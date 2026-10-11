"""Authenticated current-user avatar upload, read and reset."""

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_current_user
from app.core.storage import get_storage
from app.models.user import User, UserAvatar
from app.schemas.auth import UserInfo
from app.schemas.base import GenericResponse
from app.services.avatar import (
    MAX_AVATAR_BYTES,
    avatar_user_info,
    cleanup_avatar,
    normalize_avatar,
)

router = APIRouter(prefix="/users/me/avatar", tags=["users"])


@router.post("", response_model=GenericResponse[UserInfo])
def upload_avatar(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = normalize_avatar(file.file.read(MAX_AVATAR_BYTES + 1))
    storage = get_storage()
    avatar = db.get(UserAvatar, current_user.id)
    previous = avatar.location if avatar else None
    location = storage.save_upload(
        BytesIO(content), current_user.id, "avatar.webp", category="avatars"
    )
    if avatar is None:
        avatar = UserAvatar(user_id=current_user.id, location=location)
        db.add(avatar)
    else:
        avatar.location = location
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        cleanup_avatar(storage, location)
        raise
    if previous:
        cleanup_avatar(storage, previous)
    return GenericResponse(data=avatar_user_info(current_user, db))


@router.get("", response_class=Response)
def read_avatar(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    avatar = db.get(UserAvatar, current_user.id)
    storage = get_storage()
    if avatar is None or not storage.exists(avatar.location):
        raise HTTPException(404, "尚未设置头像")
    return Response(
        content=storage.read_bytes(avatar.location),
        media_type="image/webp",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("", response_model=GenericResponse[UserInfo])
def remove_avatar(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    avatar = db.get(UserAvatar, current_user.id)
    if avatar:
        location = avatar.location
        db.delete(avatar)
        db.commit()
        cleanup_avatar(get_storage(), location)
    return GenericResponse(data=avatar_user_info(current_user, db))
