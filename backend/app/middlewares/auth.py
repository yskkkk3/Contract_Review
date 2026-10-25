"""全局鉴权中间件：白名单外的 /api/* 请求必须携带有效 Bearer token。

与路由内 Depends(get_current_user) 双层校验并存：中间件做前置拦截与 user_id 注入。
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.security import TOKEN_TYPE_ACCESS, _is_revoked, decode_token, renew_access_token

RENEWED_ACCESS_TOKEN_HEADER = "X-Access-Token"

# Only these API operations are anonymous; user-management subpaths are protected.
PUBLIC_OPERATIONS = {
    ("POST", "/api/auth/login"), ("POST", "/api/auth/refresh"),
    ("GET", "/api/auth/cas_login"), ("POST", "/api/users"),
}


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        if not self.enabled or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.method == "OPTIONS" or (request.method, request.url.path.rstrip("/")) in PUBLIC_OPERATIONS:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return Response(status_code=401, content='{"code":401,"msg":"Not authenticated"}', media_type="application/json")
        try:
            payload = decode_token(auth[7:], TOKEN_TYPE_ACCESS)
            if await _is_revoked(payload.get("user_id"), auth[7:], payload.get("sid")):
                return Response(status_code=401, content='{"code":401,"msg":"Token revoked"}', media_type="application/json")
        except Exception:
            # 携带了 token 但无效/过期：全局拦截（与路由 Depends 双层校验）
            return Response(status_code=401, content='{"code":401,"msg":"Invalid or expired token"}', media_type="application/json")
        request.state.user_id = payload.get("user_id")
        response = await call_next(request)
        if response.status_code != 401:
            renewed_token = await renew_access_token(payload, auth[7:])
            if renewed_token:
                response.headers[RENEWED_ACCESS_TOKEN_HEADER] = renewed_token
        return response
