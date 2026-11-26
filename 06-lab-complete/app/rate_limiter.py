"""
Rate limiting (tiêu chí 7) — Sliding window lưu trong Redis.
"""
import logging
import time
import uuid

from fastapi import HTTPException
import redis

from app.config import settings
from app.redis_client import r

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây."""
    if r is None:
        return

    limit = settings.rate_limit_per_minute
    now = time.time()
    window_start = now - WINDOW_SECONDS
    redis_key = f"rate_limit:{key}"

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= limit:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = (
                max(1, int(WINDOW_SECONDS - (now - oldest[0][1])) + 1)
                if oldest
                else WINDOW_SECONDS
            )
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({limit} requests per minute)",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS + 10)
        pipe.execute()
    except HTTPException:
        raise
    except redis.RedisError as exc:
        logger.warning("redis_rate_limit_unavailable: %s", exc)
