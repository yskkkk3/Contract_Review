"""Context builder: merge top-k evidence with citation metadata into LLM context."""
from dataclasses import dataclass

from app.rag.ingest.chunker import Chunk
from app.rag.retrievers.hybrid import RetrievedChunk


@dataclass
class EvidenceContext:
    text: str
    visible: list[RetrievedChunk]
    omitted: list[str]


def assemble_context(evidence: list[RetrievedChunk], max_chars: int = 7000) -> EvidenceContext:
    """只展示完整证据块，记录未展示项，引用不得指向被预算剔除的正文。"""
    parts: list[str] = []
    visible: list[RetrievedChunk] = []
    omitted: list[str] = []
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
        size = len(seg) + (2 if parts else 0)
        if used + size > max_chars:
            omitted.append(c.doc_id)
            continue
        parts.append(seg)
        visible.append(item)
        used += size
    if parts:
        text = "\n\n".join(parts)
    elif evidence:
        text = "（检索已命中，但完整证据超出当前展示预算；未完成依据核验，须补查。）"
    else:
        text = "（未检索到相关制度/法规依据）"
    return EvidenceContext(text, visible, omitted)


def build_context(evidence: list[RetrievedChunk], max_chars: int = 3000) -> str:
    """兼容普通上下文调用；法律审阅路径另携带实际可见证据及覆盖检查。"""
    return assemble_context(evidence, max_chars).text
