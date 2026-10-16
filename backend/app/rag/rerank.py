"""Cross-encoder 排序后，以有限文档候选复核证据对问题的实际支持。"""
import asyncio
import json
import logging

from app.agent.prompts import load_prompt
from app.core.config import get_settings
from app.rag.client import _extract_json, get_sf_client
from app.rag.retrievers.hybrid import RetrievedChunk

settings = get_settings()
logger = logging.getLogger(__name__)


async def rerank_chunks(
    query: str,
    candidates: list[RetrievedChunk],
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Cross-encoder 精排：对候选重排并取 Top-K。"""
    top_k = top_k or settings.rag_rerank_top_k
    if not candidates:
        return []
    if len(candidates) <= 1:
        return candidates[:top_k]

    # 条文离开标题后容易混淆国家/地方规则；将文档身份与章节一并交给精排。
    documents = [
        f"文档：{c.chunk.doc_id}\n章节：{c.chunk.section or '未标注'}\n{c.chunk.text}"
        for c in candidates
    ]
    results = await get_sf_client().rerank(query, documents, top_n=min(top_k, len(candidates)))
    # SiliconFlow rerank 返回 relevance_score（OpenAI 兼容格式），兼容两种字段名；
    # 注意 r["index"] 是候选在 documents 中的下标，不能用 Python 对象 id 查映射。
    score_map = {
        r["index"]: r.get("score", r.get("relevance_score", 0.0)) for r in results
    }
    ordered = sorted(
        enumerate(candidates), key=lambda x: score_map.get(x[0], 0.0), reverse=True
    )
    return [
        RetrievedChunk(chunk=c.chunk, score=score_map.get(i, 0.0))
        for i, c in ordered[:top_k]
    ]


def _ranking_indices(data: dict | None, count: int, required: int) -> list[int] | None:
    """整份排序校验，非法编号/重复/缺项时不使用部分生成结果。"""
    indices = data.get("ranked_indices") if isinstance(data, dict) else None
    if not isinstance(indices, list) or not required <= len(indices) <= count:
        return None
    if any(type(index) is not int or not 0 <= index < count for index in indices):
        return None
    return indices if len(set(indices)) == len(indices) else None


async def rerank_evidence(
    query: str, candidates: list[RetrievedChunk], top_k: int,
) -> list[RetrievedChunk]:
    """文档级证据复核；失败、超时或排序无效时保留 cross-encoder 的顺序。"""
    per_doc: dict[str, list[RetrievedChunk]] = {}
    limit = max(top_k, min(60, max(1, settings.rag_evidence_rerank_docs)))
    for candidate in candidates:
        doc_id = candidate.chunk.doc_id
        if doc_id not in per_doc and len(per_doc) >= limit:
            continue
        per_doc.setdefault(doc_id, []).append(candidate)
    groups = list(per_doc.values())
    baseline = [group[0] for group in groups]
    if not settings.rag_evidence_rerank_enabled or len(groups) <= 1:
        return baseline[:top_k]
    required = min(top_k, len(groups))
    documents = [
        {
            "index": index, "doc_id": group[0].chunk.doc_id,
            "type": group[0].chunk.doc_type,
            "passages": [item.chunk.text for item in group[: settings.rag_per_doc_quota]],
        }
        for index, group in enumerate(groups)
    ]
    try:
        raw = await asyncio.wait_for(
            get_sf_client().chat(
                [
                    {"role": "system", "content": load_prompt(
                        "rag_evidence_rerank", n=min(len(groups), max(10, required)),
                    )},
                    {"role": "user", "content": json.dumps(
                        {"question": query, "documents": documents}, ensure_ascii=False,
                    )},
                ],
                model=settings.llm_intent_model, temperature=0, max_tokens=1024, brief=True,
                response_format={"type": "json_object"},
            ),
            timeout=settings.rag_evidence_rerank_timeout,
        )
        indices = _ranking_indices(_extract_json(raw), len(groups), required)
        if indices is None:
            logger.warning("Evidence rerank returned invalid indices; using cross-encoder order")
            return baseline[:top_k]
        return [baseline[index] for index in indices[:top_k]]
    except Exception as exc:  # noqa: BLE001 网络、供应商及解析故障不拖垮检索
        logger.warning("Evidence rerank failed (%s); using cross-encoder order", type(exc).__name__)
        return baseline[:top_k]
