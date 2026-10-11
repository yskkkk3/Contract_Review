from io import BytesIO
from pathlib import Path

from app.core.config import Settings
from app.core.storage import Storage


def _local_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        storage_backend="local",
        upload_dir=str(tmp_path / "uploads"),
        oss_bucket_dir=str(tmp_path / "parsed"),
    )


def test_local_storage_round_trip(tmp_path):
    storage = Storage(_local_settings(tmp_path))

    original = storage.save_upload(BytesIO(b"contract bytes"), 7, "contract.pdf")
    parsed = storage.save_text("合同解析文本", 7, "contract")

    assert storage.exists(original)
    assert storage.read_text(parsed) == "合同解析文本"
    with storage.materialize(original, suffix=".pdf") as path:
        assert Path(path).read_bytes() == b"contract bytes"

    storage.delete(original)
    storage.delete(parsed)
    assert not storage.exists(original)
    assert not storage.exists(parsed)


def test_storage_sanitizes_uploaded_filename(tmp_path):
    storage = Storage(_local_settings(tmp_path))
    saved = Path(storage.save_upload(BytesIO(b"safe"), 9, "../escape.pdf"))

    assert saved.parent == tmp_path / "uploads" / "9"
    assert saved.name.endswith("-escape.pdf")
