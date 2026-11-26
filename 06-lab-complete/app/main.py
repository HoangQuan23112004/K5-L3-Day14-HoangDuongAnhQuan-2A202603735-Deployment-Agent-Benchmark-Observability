"""
Production AI Agent — Part 6 Final Project
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import sys
import time
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r as redis_client, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Mỗi dòng log của app là 1 JSON object hợp lệ (tiêu chí 10)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_data = getattr(record, "extra_data", None)
        if isinstance(extra_data, dict):
            payload.update(extra_data)
        return json.dumps(payload, ensure_ascii=False)


def _setup_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()
    app_logger.addHandler(handler)
    app_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    app_logger.propagate = False
    return app_logger


logger = _setup_logging()

START_TIME = time.time()
is_shutting_down = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management & graceful shutdown (tiêu chí 11)."""
    global is_shutting_down
    is_shutting_down = False
    logger.info(
        "agent_startup",
        extra={
            "extra_data": {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
            }
        },
    )
    yield

    is_shutting_down = True
    logger.info(
        "agent_shutdown_started",
        extra={"extra_data": {"event": "shutdown"}},
    )
    if redis_client is not None:
        try:
            redis_client.close()
        except Exception:
            pass
    logger.info(
        "agent_shutdown_complete",
        extra={"extra_data": {"event": "shutdown_complete"}},
    )


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "http_request",
        extra={
            "extra_data": {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": elapsed_ms,
            }
        },
    )
    return response


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = None


@app.get("/health")
def health():
    """Liveness probe — luôn trả 200 khi process còn sống, kể cả khi Redis chết."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "environment": settings.environment,
    }


@app.get("/ready")
def ready():
    """Readiness probe — 200 khi sẵn sàng, 503 khi Redis không kết nối được hoặc đang shutdown."""
    if is_shutting_down:
        raise HTTPException(status_code=503, detail="Service is shutting down")
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready", "redis": "connected"}


@app.post("/ask")
async def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    """Protected endpoint: API Key auth + Redis rate limit + Redis cost guard."""
    check_rate_limit(api_key)
    check_budget()

    answer = await asyncio.to_thread(llm_ask, body.question)

    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost_usd = record_cost(input_tokens, output_tokens)

    logger.info(
        "agent_answered",
        extra={
            "extra_data": {
                "event": "ask_completed",
                "question_len": len(body.question),
                "answer_len": len(answer),
                "cost_usd": cost_usd,
            }
        },
    )

    return {
        "question": body.question,
        "answer": answer,
        "user_id": body.user_id,
        "cost_usd": cost_usd,
    }
