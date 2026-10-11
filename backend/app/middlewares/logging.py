"""请求日志中间件：记录 method / path / status / 耗时 / user_id（生产可接 Langfuse/ES）。"""
import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("request")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        resp = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        user_id = getattr(request.state, "user_id", None)
        logger.info(
            "%s %s -> %s %d %.1fms uid=%s",
            request.method, request.url.path, resp.status_code, duration_ms, user_id,
        )
        return resp
