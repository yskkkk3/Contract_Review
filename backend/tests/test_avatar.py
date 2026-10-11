"""Avatar routes use isolated local storage or an in-memory OSS bucket, never real OSS."""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import avatars
from app.core.config import Settings
from app.core.storage import Storage
from app.services.avatar import MAX_AVATAR_BYTES, normalize_avatar

ENDPOINT = "/api/users/me/avatar"


def test_avatar_removes_exif_and_applies_orientation():
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "Private image description"
    source = BytesIO()
    Image.new("RGB", (800, 600), "blue").save(source, format="JPEG", exif=exif)
    with Image.open(BytesIO(normalize_avatar(source.getvalue()))) as image:
        assert image.size == (384, 512)
        assert not image.getexif()


def test_avatar_rejects_decompression_bombs(monkeypatch):
    from fastapi import HTTPException

    data = image_bytes(size=(64, 64))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(HTTPException) as error:
        normalize_avatar(data)
    assert error.value.status_code == 400


class FakeBucket:
    def __init__(self):
        self.objects = {}

    def put_object(self, key, source):
        self.objects[key] = source.read()

    def get_object(self, key):
        return BytesIO(self.objects[key])

    def object_exists(self, key):
        return key in self.objects

    def delete_object(self, key):
        self.objects.pop(key, None)


@pytest.fixture(params=["local", "oss"])
def avatar_storage(request, tmp_path, monkeypatch):
    storage = Storage(Settings(
        _env_file=None,
        storage_backend=request.param,
        upload_dir=str(tmp_path / "uploads"),
        oss_bucket_name="test-bucket",
        oss_prefix="contract-review",
    ))
    if request.param == "oss":
        storage._oss_bucket = FakeBucket()
    monkeypatch.setattr(avatars, "get_storage", lambda: storage)
    return storage


def image_bytes(format="PNG", size=(800, 600)):
    output = BytesIO()
    Image.new("RGB", size, "blue").save(output, format=format)
    return output.getvalue()


def stored_objects(storage):
    if storage.backend == "oss":
        return list(storage.bucket.objects)
    return [str(path) for path in Path(storage.settings.upload_dir).rglob("*.webp")]


@pytest.mark.parametrize("method", ["get", "post", "delete"])
def test_avatar_requires_login(client, method):
    response = getattr(client, method)(ENDPOINT)
    assert response.status_code == 401


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
def test_avatar_round_trip(client, auth_headers, avatar_storage, format):
    assert client.get("/api/auth/me", headers=auth_headers).json()["data"]["avatar_url"] is None
    assert client.get(ENDPOINT, headers=auth_headers).status_code == 404
    response = client.post(
        ENDPOINT, headers=auth_headers,
        # Actual decoded bytes determine the format, not the untrusted name/MIME.
        files={"file": ("../misleading.html", image_bytes(format), "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["avatar_url"] == ENDPOINT
    assert client.get("/api/auth/me", headers=auth_headers).json()["data"]["avatar_url"] == ENDPOINT
    image_response = client.get(ENDPOINT, headers=auth_headers)
    assert image_response.headers["content-type"] == "image/webp"
    assert image_response.headers["cache-control"] == "private, no-store"
    assert image_response.headers["x-content-type-options"] == "nosniff"
    with Image.open(BytesIO(image_response.content)) as image:
        assert image.format == "WEBP"
        assert image.size == (512, 384)
        assert not image.getexif()
    objects = stored_objects(avatar_storage)
    assert len(objects) == 1
    assert "/avatars/" in objects[0].replace("\\", "/")
    assert objects[0].endswith("-avatar.webp")


def test_replace_and_reset_delete_previous_objects(client, auth_headers, avatar_storage):
    for _ in range(2):
        response = client.post(
            ENDPOINT, headers=auth_headers, files={"file": ("avatar.png", image_bytes(), "image/png")}
        )
        assert response.status_code == 200
        assert len(stored_objects(avatar_storage)) == 1
    assert client.delete(ENDPOINT, headers=auth_headers).json()["data"]["avatar_url"] is None
    assert stored_objects(avatar_storage) == []
    assert client.get(ENDPOINT, headers=auth_headers).status_code == 404
    assert client.get("/api/auth/me", headers=auth_headers).json()["data"]["avatar_url"] is None
    assert client.delete(ENDPOINT, headers=auth_headers).status_code == 200


def test_five_mb_boundary_and_invalid_upload_preserve_saved_avatar(client, auth_headers, avatar_storage):
    original = image_bytes()
    exactly_five_mb = original + b"\0" * (MAX_AVATAR_BYTES - len(original))
    response = client.post(
        ENDPOINT, headers=auth_headers, files={"file": ("avatar.png", exactly_five_mb, "image/png")}
    )
    assert response.status_code == 200
    previous = stored_objects(avatar_storage)
    previous_bytes = client.get(ENDPOINT, headers=auth_headers).content
    for data, expected_status in [
        (exactly_five_mb + b"\0", 413),
        (b"<svg onload='alert(1)'/>", 400),
        (b"not a picture", 400),
        (b"", 400),
        (image_bytes("GIF"), 400),
    ]:
        response = client.post(
            ENDPOINT, headers=auth_headers, files={"file": ("avatar.jpg", data, "image/jpeg")}
        )
        assert response.status_code == expected_status, response.text
        assert stored_objects(avatar_storage) == previous
        assert client.get(ENDPOINT, headers=auth_headers).content == previous_bytes


def test_avatar_is_scoped_to_current_user(client, auth_headers, avatar_storage):
    response = client.post(
        ENDPOINT, headers=auth_headers, files={"file": ("avatar.png", image_bytes(), "image/png")}
    )
    assert response.status_code == 200
    first_image = client.get(ENDPOINT, headers=auth_headers).content
    client.post("/api/users", json={"username": "another", "password": "secret123"})
    login = client.post("/api/auth/login", json={"identifier": "another", "password": "secret123"})
    second_headers = {"Authorization": "Bearer " + login.json()["data"]["access_token"]}
    assert client.get(ENDPOINT, headers=second_headers).status_code == 404
    assert client.delete(ENDPOINT, headers=second_headers).status_code == 200
    assert client.get(ENDPOINT, headers=auth_headers).content == first_image
    response = client.post(
        ENDPOINT, headers=second_headers,
        files={"file": ("second.png", image_bytes(size=(32, 32)), "image/png")},
    )
    assert response.status_code == 200
    assert len(stored_objects(avatar_storage)) == 2
    assert client.get(ENDPOINT, headers=auth_headers).content == first_image


def test_database_failure_removes_new_object(client, auth_headers, avatar_storage, monkeypatch):
    def fail_commit(_session):
        raise SQLAlchemyError("Simulated database failure")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        with pytest.raises(SQLAlchemyError):
            client.post(
                ENDPOINT, headers=auth_headers,
                files={"file": ("avatar.png", image_bytes(), "image/png")},
            )
    assert stored_objects(avatar_storage) == []
    assert client.get("/api/auth/me", headers=auth_headers).json()["data"]["avatar_url"] is None
