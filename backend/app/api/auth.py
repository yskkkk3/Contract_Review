"""Auth routes: login / refresh / logout / me / CAS placeholder."""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.cache import acquire_lock, release_lock
from app.core.config import get_settings
from app.core.db import get_db
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, RefreshTokenRequest, UserInfo
from app.schemas.base import GenericResponse
from app.services.avatar import avatar_user_info

router = APIRouter(tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=GenericResponse[LoginResponse])
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    # Redis 并发登录锁：同一用户短窗口内仅允许一次登录，防高频互踢
    lock_key = f"login_lock:{request.identifier}"
    lock_token = f"{request.identifier}-{id(request)}"
    if not await acquire_lock(lock_key, lock_token, ttl=5):
        raise HTTPException(status_code=429, detail="登录过于频繁，请稍后重试")
    user = db.query(User).filter(User.username == request.identifier).first()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(401, "Incorrect username or password")
    if not user.is_active:
        raise HTTPException(403, "User disabled")

    session_id = secrets.token_urlsafe(32)
    access_token = create_access_token(user.username, user.id, session_id)
    refresh_token = create_refresh_token(user.username, user.id, session_id)
    redis = get_redis()
    await redis.set(
        f"access_token:{user.id}",
        session_id,
        ex=settings.access_token_expire_minutes * 60,
    )
    await redis.set(f"refresh_token:{user.id}", refresh_token, ex=settings.refresh_token_expire_days * 86400)
    await release_lock(lock_key, lock_token)
    return GenericResponse(data=LoginResponse(access_token=access_token, refresh_token=refresh_token))


@router.post("/refresh", response_model=GenericResponse[LoginResponse])
async def refresh(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    payload = decode_token(request.refresh_token, expected_type="refresh")
    user_id = payload.get("user_id")
    redis = get_redis()
    stored = await redis.get(f"refresh_token:{user_id}")
    if stored != request.refresh_token:
        raise HTTPException(401, "Refresh token revoked or invalid")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "User invalid")
    session_id = payload.get("sid") or secrets.token_urlsafe(32)
    access_token = create_access_token(user.username, user.id, session_id)
    refresh_token = request.refresh_token
    if payload.get("sid") is None:
        # 首次刷新旧版 token 时迁移到带 sid 的滑动会话。
        refresh_token = create_refresh_token(user.username, user.id, session_id)
        await redis.set(
            f"refresh_token:{user.id}",
            refresh_token,
            ex=settings.refresh_token_expire_days * 86400,
        )
    await redis.set(
        f"access_token:{user.id}",
        session_id,
        ex=settings.access_token_expire_minutes * 60,
    )
    return GenericResponse(
        data=LoginResponse(access_token=access_token, refresh_token=refresh_token)
    )


@router.post("/logout", response_model=GenericResponse)
async def logout(current_user: User = Depends(get_current_user)):
    redis = get_redis()
    await redis.delete(f"access_token:{current_user.id}", f"refresh_token:{current_user.id}")
    return GenericResponse(msg="logout success")


@router.get("/me", response_model=GenericResponse[UserInfo])
async def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return GenericResponse(data=avatar_user_info(current_user, db))


@router.get("/cas_login", response_model=None)
async def cas_login():
    """CAS 预留：配置 cas_server_url 后跳转学校统一身份认证。"""
    if not settings.cas_server_url:
        raise HTTPException(501, "CAS not configured")
    return RedirectResponse(url=f"{settings.cas_server_url}/login?service={settings.frontend_url}/auth/cas")
