from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, HTTPException, status
import redis

from app.core.config import get_settings


_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    """Lazy Redis connection — returns None if Redis is unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(get_settings().REDIS_URL)
            _redis_client.ping()
        except Exception:
            return None
    return _redis_client


def rate_limiter(max_per_day: int = 30) -> Callable:
    async def _middleware(request: Request, call_next):
        user = getattr(request.state, "user", None)
        if not user:
            return await call_next(request)
        r = get_redis()
        if r is None:
            # Redis unavailable — skip rate limiting
            return await call_next(request)
        key = f"rate:{user['id']}:{time.strftime('%Y-%m-%d')}"
        val = r.incr(key)
        if val == 1:
            r.expire(key, 86400)
        if val > max_per_day:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={"detail": "Rate limit exceeded"})
        return await call_next(request)

    return _middleware


