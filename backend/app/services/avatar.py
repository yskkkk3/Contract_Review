"""Avatar image validation and serialization, using the shared storage backend."""

import logging
import warnings
from io import BytesIO

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.storage import Storage
from app.models.user import User, UserAvatar
from app.schemas.auth import UserInfo

MAX_AVATAR_BYTES = 5 * 1024 * 1024
AVATAR_URL = "/api/users/me/avatar"
logger = logging.getLogger(__name__)


def normalize_avatar(data: bytes) -> bytes:
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(413, "头像大小不能超过 5 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=("JPEG", "PNG", "WEBP")) as image:
                image.load()
                normalized = ImageOps.exif_transpose(image)
                normalized.thumbnail((512, 512), Image.Resampling.LANCZOS)
                output = BytesIO()
                # Re-encode pixels only: no original EXIF/GPS or appended file payload.
                normalized.convert("RGBA").save(output, format="WEBP", quality=90)
                return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise HTTPException(400, "请上传有效的 JPG、PNG 或 WebP 图片") from exc


def avatar_user_info(user: User, db: Session) -> UserInfo:
    return UserInfo(
        id=user.id,
        username=user.username,
        role=user.role,
        avatar_url=AVATAR_URL if db.get(UserAvatar, user.id) else None,
    )


def cleanup_avatar(storage: Storage, location: str) -> None:
    """A failed old-object cleanup must not undo a successfully saved profile."""
    try:
        storage.delete(location)
    except Exception:
        logger.warning("Failed to clean up an avatar object", exc_info=True)
