"""Redis 滑动窗口限流中间件：按 IP（或 user_id）限制每分钟请求数。"""
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.cache import cache_get, cache_set
from app.core.config import get_settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool | None = None, per_minute: int | None = None):
        super().__init__(app)
        s = get_settings()
        self.enabled = s.rate_limit_enabled if enabled is None else enabled
        self.per_minute = s.rate_limit_per_minute if per_minute is None else per_minute

    async def dispatch(self, request: Request, call_next):
        if not self.enabled or request.url.path.startswith(("/docs", "/redoc", "/openapi.json", "/health")):
            return await call_next(request)
        key = f"rl:{request.client.host}:{int(time.time() // 60)}"
        count = int(await cache_get(key) or "0") + 1
        await cache_set(key, str(count), ttl=120)
        if count > self.per_minute:
            return Response(status_code=429, content='{"code":429,"msg":"rate limit exceeded"}', media_type="application/json")
        return await call_next(request)
