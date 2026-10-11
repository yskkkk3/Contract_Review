"""JWT auth: create/verify tokens, password hashing, current-user dependency."""
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.redis import get_redis
from app.models.user import User

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """PBKDF2-SHA256，存储格式: pbkdf2_sha256$iterations$salt_hex$hash_hex"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", plain.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def _create_token(sub: str, user_id: int, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "user_id": user_id,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(sub: str, user_id: int) -> str:
    return _create_token(
        sub, user_id, TOKEN_TYPE_ACCESS,
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(sub: str, user_id: int) -> str:
    return _create_token(
        sub, user_id, TOKEN_TYPE_REFRESH,
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: str | None = None) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc
    if expected_type and payload.get("type") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    return payload


async def _is_revoked(user_id: int, token: str) -> bool:
    """Redis 校验：登出后 token 被吊销，返回 True。"""
    redis = get_redis()
    stored = await redis.get(f"access_token:{user_id}")
    if stored is None:
        return True
    return stored != token


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = decode_token(credentials.credentials, TOKEN_TYPE_ACCESS)
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token payload")
    if await _is_revoked(user_id, credentials.credentials):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or missing")
    return user
