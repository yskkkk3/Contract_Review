"""Unified local/Alibaba Cloud OSS storage for contract artifacts."""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote
from uuid import uuid4

import oss2

from app.core.config import Settings, get_settings


class StorageError(RuntimeError):
    """Raised when the configured storage backend cannot complete an operation."""


class Storage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.backend = self.settings.storage_backend.strip().lower()
        if self.backend not in {"local", "oss"}:
            raise StorageError("STORAGE_BACKEND must be 'local' or 'oss'")
        self._oss_bucket: oss2.Bucket | None = None

    @property
    def bucket(self) -> oss2.Bucket:
        if self.backend != "oss":
            raise StorageError("OSS bucket requested while STORAGE_BACKEND is not 'oss'")
        if self._oss_bucket is None:
            required = {
                "OSS_ENDPOINT": self.settings.oss_endpoint,
                "OSS_ACCESS_KEY_ID": self.settings.oss_access_key_id,
                "OSS_ACCESS_KEY_SECRET": self.settings.oss_access_key_secret,
                "OSS_BUCKET_NAME": self.settings.oss_bucket_name,
            }
            missing = [name for name, value in required.items() if not value.strip()]
            if missing:
                raise StorageError(f"Missing OSS configuration: {', '.join(missing)}")
            auth = oss2.Auth(
                self.settings.oss_access_key_id,
                self.settings.oss_access_key_secret,
            )
            self._oss_bucket = oss2.Bucket(
                auth,
                self.settings.oss_endpoint,
                self.settings.oss_bucket_name,
            )
        return self._oss_bucket

    def _object_key(self, category: str, user_id: int, filename: str) -> str:
        safe_name = Path(filename).name or "file"
        prefix = self.settings.oss_prefix.strip("/")
        parts = [part for part in (prefix, category, str(user_id)) if part]
        parts.append(f"{uuid4().hex}-{safe_name}")
        return "/".join(parts)

    def _oss_uri(self, key: str) -> str:
        return f"oss://{self.settings.oss_bucket_name}/{key}"

    def _parse_oss_uri(self, uri: str) -> str:
        if not uri.startswith("oss://"):
            raise StorageError(f"Not an OSS URI: {uri}")
        bucket_name, separator, key = uri[6:].partition("/")
        if not separator or not key:
            raise StorageError(f"Invalid OSS URI: {uri}")
        if bucket_name != self.settings.oss_bucket_name:
            raise StorageError(f"OSS URI belongs to an unexpected bucket: {bucket_name}")
        return key

    def save_upload(self, source: BinaryIO, user_id: int, filename: str) -> str:
        """Persist an uploaded binary stream and return a local path or oss:// URI."""
        if self.backend == "oss":
            key = self._object_key("uploads", user_id, filename)
            self.bucket.put_object(key, source)
            return self._oss_uri(key)

        save_dir = Path(self.settings.upload_dir) / str(user_id)
        save_dir.mkdir(parents=True, exist_ok=True)
        path = save_dir / f"{uuid4().hex}-{Path(filename).name}"
        with path.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        return str(path)

    def save_text(self, text: str, user_id: int, filename: str) -> str:
        """Persist UTF-8 parsed text and return a local path or oss:// URI."""
        safe_name = f"{Path(filename).stem or 'contract'}.txt"
        if self.backend == "oss":
            key = self._object_key("parsed", user_id, safe_name)
            self.bucket.put_object(key, text.encode("utf-8"))
            return self._oss_uri(key)

        save_dir = Path(self.settings.oss_bucket_dir) / str(user_id)
        save_dir.mkdir(parents=True, exist_ok=True)
        path = save_dir / f"{uuid4().hex}-{safe_name}"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def read_text(self, location: str) -> str:
        if location.startswith("oss://"):
            key = self._parse_oss_uri(location)
            return self.bucket.get_object(key).read().decode("utf-8")
        return Path(location).read_text(encoding="utf-8")

    def exists(self, location: str) -> bool:
        if location.startswith("oss://"):
            return self.bucket.object_exists(self._parse_oss_uri(location))
        return Path(location).exists()

    def delete(self, location: str) -> None:
        if not location:
            return
        if location.startswith("oss://"):
            self.bucket.delete_object(self._parse_oss_uri(location))
            return
        Path(location).unlink(missing_ok=True)

    @contextmanager
    def materialize(self, location: str, suffix: str = "") -> Iterator[str]:
        """Yield a local path, downloading an OSS object to a temporary file if needed."""
        if not location.startswith("oss://"):
            yield location
            return

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            temp_path = Path(temporary.name)
        try:
            self.bucket.get_object_to_file(self._parse_oss_uri(location), str(temp_path))
            yield str(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def signed_download_url(self, location: str, filename: str, expires: int = 300) -> str:
        if not location.startswith("oss://"):
            raise StorageError("Signed URLs are only available for OSS objects")
        disposition = f"attachment; filename*=UTF-8''{quote(Path(filename).name)}"
        return self.bucket.sign_url(
            "GET",
            self._parse_oss_uri(location),
            expires,
            params={"response-content-disposition": disposition},
        )


@lru_cache
def get_storage() -> Storage:
    return Storage()
