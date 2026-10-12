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
        provenance = "；".join(
            f"{label}：{c.meta[key]}"
            for key, label in [
                ("law_name", "文件"), ("legal_level", "层级"), ("version", "版本"),
                ("effective_date", "施行"), ("verified_at", "来源核对日期"),
                ("articles", "条文范围"), ("scope", "适用范围"), ("content_kind", "内容性质"),
            ]
            if c.meta.get(key)
        )
        if not provenance:
            provenance = "自建示例，仅供起草参考" if c.doc_type == "template" else "版本及现行效力未标注，适用前需核实"
        seg = (
            f"[{c.doc_type}] doc_id={c.doc_id}\n来源：{c.source}\n"
            f"章节：{c.section or '未标注'}；{provenance}\n{c.text}"
        )
        if used + len(seg) > max_chars:
            break
        parts.append(seg)
        used += len(seg)
    return "\n\n".join(parts) if parts else "（未检索到相关制度/法规依据）"
