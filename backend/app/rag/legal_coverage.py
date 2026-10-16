"""Curated legal facets: disclose missing conditions instead of assuming applicability."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.rag.context import assemble_context
from app.rag.ingest.chunker import Chunk
from app.rag.retrievers.hybrid import RetrievedChunk
from app.rag.retrievers.sparse_bm25 import BM25Index

CHECKS_PATH = Path(__file__).resolve().parents[2] / "data" / "kb" / "legal_checks.json"


@lru_cache(maxsize=1)
def legal_profiles() -> list[dict]:
    return json.loads(CHECKS_PATH.read_text(encoding="utf-8"))["profiles"]


def matching_profiles(query: str, risk_dim: str | None = None) -> list[dict]:
    return [profile for profile in legal_profiles()
            if (not risk_dim or risk_dim in profile["risk_dims"])
            and any(term in query for term in profile["triggers"])
            and not any(term in query for term in profile.get("exclude", []))]


def merge_document(chunks: list[Chunk]) -> Chunk:
    """重新拼接实际入库段落与条号；跨块的50字overlap只保留一次。"""
    first = chunks[0]
    text = ""
    section = None
    for chunk in chunks:
        if chunk.section != section:
            section = chunk.section
            if section:
                text += f"\n{section}\n"
        body = chunk.text
        if body in text:
            continue
        overlap = 0
        for size in range(min(len(text), len(body), 100), 0, -1):
            if text.endswith(body[:size]):
                overlap = size
                break
        text += ("\n" if text and not overlap else "") + body[overlap:]
    return Chunk(text.strip(), first.doc_id, first.source, first.doc_type,
                 "关联条文（原索引顺序）", dict(first.meta))


def supplemental_evidence(profiles: list[dict], index: BM25Index) -> list[RetrievedChunk]:
    """按已核对的法律主题取完整关联条文；缺失资料绝不由清单文字冒充证据。"""
    doc_ids = dict.fromkeys(facet["document"] for profile in profiles for facet in profile["facets"])
    results = []
    for doc_id in doc_ids:
        chunks = index.document_chunks(doc_id)
        if chunks:
            results.append(RetrievedChunk(merge_document(chunks), 0.0))
    return results


@dataclass
class CoverageResult:
    facets: list[dict]
    facts: list[str]

    @property
    def missing(self) -> list[str]:
        return [f"{facet['profile']}/{facet['id']}" for facet in self.facets if not facet["covered"]]

    def render(self) -> str:
        lines = ["【关键规则覆盖检查：只说明资料是否展示，不表示交易事实或法律适用已确认】"]
        lines.extend(f"- 适用条件核对项（已明确事实直接采用，仅缺失事项待核实）：{fact}" for fact in self.facts)
        lines.extend(f"- {facet['profile']}/{facet['id']}（{facet['kind']}）："
                     f"{'正文及版本来源可见' if facet['covered'] else '依据未完整展示，须补查'}"
                     for facet in self.facets)
        return "\n".join(lines)


def check_coverage(profiles: list[dict], visible: list[RetrievedChunk]) -> CoverageResult:
    """只核验实际可见正文及来源元数据，不把清单、标题或另一个版本当作证明。"""
    documents: dict[str, list[Chunk]] = {}
    for item in visible:
        documents.setdefault(item.chunk.doc_id, []).append(item.chunk)
    facets = []
    for profile in profiles:
        for facet in profile["facets"]:
            candidates = documents.get(facet["document"], [])
            covered = any(
                chunk.meta.get("verified_at") and chunk.meta.get("version")
                and all(needle in chunk.text for needle in facet["needles"])
                for chunk in candidates
            )
            facets.append({**facet, "profile": profile["id"], "covered": bool(covered)})
    return CoverageResult(facets, list(dict.fromkeys(fact for p in profiles for fact in p["facts"])))


@dataclass
class LegalContext:
    text: str
    evidence: list[RetrievedChunk]
    coverage: CoverageResult


def legal_context(
    query: str, risk_dim: str | None, index: BM25Index,
    retrieved: list[RetrievedChunk] | None = None, max_chars: int = 7000,
) -> LegalContext:
    profiles = matching_profiles(query, risk_dim)
    supplements = supplemental_evidence(profiles, index)
    # 同文档完整关联条文优先，不让单个最佳chunk替换含关键例外的完整证据。
    combined = list(supplements)
    seen = {item.chunk.doc_id for item in combined}
    for item in retrieved or []:
        if item.chunk.doc_id not in seen:
            combined.append(item)
            seen.add(item.chunk.doc_id)
    if not profiles:
        assembled = assemble_context(combined, max_chars)
        return LegalContext(assembled.text if combined else "", assembled.visible, CoverageResult([], []))
    pending = check_coverage(profiles, [])
    reserve = len(pending.render()) + 120
    if reserve >= max_chars:
        return LegalContext("（核验清单超出展示预算，关键规则未完成核验，须分项补查。）", [], pending)
    assembled = assemble_context(combined, max_chars - reserve)
    coverage = check_coverage(profiles, assembled.visible)
    text = f"{coverage.render()}\n\n【实际可见的依据正文】\n{assembled.text}"
    return LegalContext(text, assembled.visible, coverage)
