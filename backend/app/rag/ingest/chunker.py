"""Structured chunker: split by heading levels with overlap + metadata."""
import re
from dataclasses import dataclass, field

HEADING_RE = re.compile(r"^(第[一二三四五六七八九十百千0-9]+[章节条款条]|[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|\(\d+\)|\d+[\.、])")


@dataclass
class Chunk:
    text: str
    doc_id: str
    source: str
    doc_type: str  # regulation | institution | template
    section: str = ""
    meta: dict = field(default_factory=dict)


def _strip_heading(line: str) -> tuple[str, str]:
    """若行首是标题，返回 (标题, 去标题后的文本)；否则 ("", line)。"""
    if HEADING_RE.match(line.strip()):
        match = HEADING_RE.match(line.strip())
        title = match.group(0)
        return title, line.strip()[len(title):]
    return "", line


def chunk_document(
    text: str,
    doc_id: str,
    source: str,
    doc_type: str,
    max_chars: int = 500,
    overlap: int = 50,
) -> list[Chunk]:
    """按标题层级 + 段落切分，带 overlap 与 section 元数据。

    策略（简历可写点）：
    - 优先按标题切分，保证语义完整性；
    - 超长标题段再按 max_chars 切分并加 overlap，避免跨块断句；
    - 每个 chunk 携带 {doc_id, source, doc_type, section} 元数据，支持分层过滤。
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    chunks: list[Chunk] = []
    current_section = ""
    buf: list[str] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        body = "\n".join(buf)
        if len(body) <= max_chars:
            chunks.append(
                Chunk(
                    text=body, doc_id=doc_id, source=source,
                    doc_type=doc_type, section=current_section,
                )
            )
        else:
            # 超长：按 max_chars 切分 + overlap
            start = 0
            while start < len(body):
                end = min(start + max_chars, len(body))
                seg = body[start:end]
                chunks.append(
                    Chunk(
                        text=seg, doc_id=doc_id, source=source,
                        doc_type=doc_type, section=current_section,
                    )
                )
                if end >= len(body):
                    break
                start = max(end - overlap, start + 1)
        buf = []

    for line in lines:
        title, rest = _strip_heading(line)
        if title:
            flush()
            current_section = title.strip()
            if rest.strip():
                buf.append(rest.strip())
        else:
            buf.append(line.strip())
    flush()
    return chunks
