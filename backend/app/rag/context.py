"""Context builder: merge top-k evidence with citation metadata into LLM context."""
from app.rag.ingest.chunker import Chunk
from app.rag.retrievers.hybrid import RetrievedChunk


def build_context(evidence: list[RetrievedChunk], max_chars: int = 3000) -> str:
    """拼接检索证据，每条带 [来源] 标注，供 Specialist 引用。

    简历点：上下文可追溯——每条依据带 source/section，防止模型编造法规。
    """
    parts: list[str] = []
    used = 0
    for item in evidence:
        c: Chunk = item.chunk
        seg = f"[{c.doc_type}] {c.section or c.source}\n{c.text}"
        if used + len(seg) > max_chars:
            break
        parts.append(seg)
        used += len(seg)
    return "\n\n".join(parts) if parts else "（未检索到相关制度/法规依据）"
