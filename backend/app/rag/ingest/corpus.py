"""Offline corpus loading with optional, explicitly verified source metadata."""
import json
from pathlib import Path


def load_corpus(data_dir: str | Path) -> list[dict]:
    """Load local text and retain official provenance without inventing legacy metadata."""
    data_dir = Path(data_dir)
    manifest_path = data_dir / "sources.json"
    sources = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    docs: list[dict] = []
    for layer, folder in [
        ("institution", "institution"), ("regulation", "regulation"), ("template", "templates"),
    ]:
        for path in sorted((data_dir / folder).glob("*.txt")):
            metadata = sources.get(path.relative_to(data_dir).as_posix(), {})
            docs.append({
                "title": path.stem,
                "source": metadata.get("source", path.resolve().as_uri()),
                "doc_type": layer,
                "text": path.read_text(encoding="utf-8"),
                "meta": {key: value for key, value in metadata.items() if key != "source"},
            })
    return docs
