"""Rerank with bge-reranker-v2-m3 (cross-encoder) for precision."""
from app.core.config import get_settings
from app.rag.client import get_sf_client
from app.rag.retrievers.hybrid import RetrievedChunk

settings = get_settings()


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

    documents = [c.chunk.text for c in candidates]
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
