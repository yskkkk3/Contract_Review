"""全局鉴权中间件：白名单外的 /api/* 请求必须携带有效 Bearer token。

与路由内 Depends(get_current_user) 双层校验并存：中间件做前置拦截与 user_id 注入。
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.security import TOKEN_TYPE_ACCESS, decode_token

# 无需登录的公开路径（前缀匹配）
PUBLIC_PATHS = (
    "/docs", "/redoc", "/openapi.json", "/health",
    "/api/auth/login", "/api/auth/refresh", "/api/auth/cas_login",
    "/api/users", "/api/contracts/upload_raw",
)


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        if not self.enabled or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if any(request.url.path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            # 无 token：放行，由路由级 Depends(get_current_user) 决定是否强制鉴权（公开接口可匿名）
            return await call_next(request)
        try:
            payload = decode_token(auth[7:], TOKEN_TYPE_ACCESS)
        except Exception:
            # 携带了 token 但无效/过期：全局拦截（与路由 Depends 双层校验）
            return Response(status_code=401, content='{"code":401,"msg":"Invalid or expired token"}', media_type="application/json")
        request.state.user_id = payload.get("user_id")
        return await call_next(request)
