"""
Cost guard (tiêu chí 8) — Cộng dồn chi phí LLM vào Redis, chặn với HTTP 402 khi vượt ngân sách.
"""
import logging
import time

from fastapi import HTTPException
import redis

from app.config import settings
from app.redis_client import r

logger = logging.getLogger(__name__)

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

# Fallback in-memory khi Redis chưa sẵn sàng
_fallback_daily_cost: float = 0.0
_fallback_day: str = time.strftime("%Y-%m-%d")


def _daily_key() -> str:
    return f"cost:daily:{time.strftime('%Y-%m-%d')}"


def _monthly_key() -> str:
    return f"cost:monthly:{time.strftime('%Y-%m')}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    global _fallback_daily_cost, _fallback_day

    daily_cost = 0.0
    monthly_cost = 0.0

    if r is not None:
        try:
            daily_cost = float(r.get(_daily_key()) or 0.0)
            monthly_cost = float(r.get(_monthly_key()) or 0.0)
        except redis.RedisError as exc:
            logger.warning("redis_cost_check_unavailable: %s", exc)
            today = time.strftime("%Y-%m-%d")
            if _fallback_day != today:
                _fallback_day = today
                _fallback_daily_cost = 0.0
            daily_cost = _fallback_daily_cost
    else:
        today = time.strftime("%Y-%m-%d")
        if _fallback_day != today:
            _fallback_day = today
            _fallback_daily_cost = 0.0
        daily_cost = _fallback_daily_cost

    if daily_cost >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Daily budget exceeded (${daily_cost:.6f} / ${settings.daily_budget_usd:.4f})",
        )
    if monthly_cost >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Monthly budget exceeded (${monthly_cost:.6f} / ${settings.monthly_budget_usd:.4f})",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    global _fallback_daily_cost, _fallback_day

    cost = round(
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K,
        8,
    )

    today = time.strftime("%Y-%m-%d")
    if _fallback_day != today:
        _fallback_day = today
        _fallback_daily_cost = 0.0
    _fallback_daily_cost += cost

    if r is not None:
        try:
            d_key = _daily_key()
            m_key = _monthly_key()
            pipe = r.pipeline()
            pipe.incrbyfloat(d_key, cost)
            pipe.expire(d_key, 86400 * 2)
            pipe.incrbyfloat(m_key, cost)
            pipe.expire(m_key, 86400 * 35)
            pipe.execute()
        except redis.RedisError as exc:
            logger.warning("redis_cost_record_unavailable: %s", exc)

    return cost
