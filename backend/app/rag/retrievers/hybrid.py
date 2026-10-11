"""Hybrid retriever: dense (Qdrant + bge-m3) + sparse (BM25) -> RRF fusion.

简历点：双路召回互补（语义泛化 + 关键词精确），RRF 融合避免异构分数
直接相加的尺度问题，再由 Cross-encoder 精排提精度。
"""
import hashlib
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings
from app.rag.client import get_sf_client
from app.rag.ingest.chunker import Chunk
from app.rag.retrievers.sparse_bm25 import BM25Index

settings = get_settings()


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float


def rrf_fusion(
    dense_ranked: list[Chunk],
    sparse_ranked: list[Chunk],
    k: int = 60,
) -> list[tuple[Chunk, float]]:
    """Reciprocal Rank Fusion：score = Σ 1/(k + rank)。"""
    fused: dict[str, list[float]] = {}
    chunks_by_key: dict[str, Chunk] = {}

    def key(c: Chunk) -> str:
        return hashlib.md5(f"{c.doc_id}:{c.text[:80]}".encode()).hexdigest()

    for rank, chunk in enumerate(dense_ranked):
        kk = key(chunk)
        fused.setdefault(kk, []).append(1.0 / (k + rank + 1))
        chunks_by_key[kk] = chunk
    for rank, chunk in enumerate(sparse_ranked):
        kk = key(chunk)
        fused.setdefault(kk, []).append(1.0 / (k + rank + 1))
        chunks_by_key[kk] = chunk

    scored = [(chunks_by_key[kk], sum(scores)) for kk, scores in fused.items()]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


class HybridRetriever:
    def __init__(self, qdrant: AsyncQdrantClient, bm25: BM25Index) -> None:
        self.qdrant = qdrant
        self.bm25 = bm25

    async def retrieve(
        self,
        query: str,
        collection: str,
        top_k: int = 60,
        doc_type: str | None = None,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        """双路召回 → RRF 融合 → 返回按融合分排序的 chunks。"""
        sf = get_sf_client()

        # ---- dense 路：Qdrant 向量检索 ----
        q_vector = (await sf.embed([query]))[0]
        q_filter = None
        conditions: list[models.FieldCondition] = []
        if doc_type:
            conditions.append(
                models.FieldCondition(key="doc_type", match=models.MatchValue(value=doc_type))
            )
        if filters:
            for field, value in filters.items():
                conditions.append(
                    models.FieldCondition(key=field, match=models.MatchValue(value=value))
                )
        if conditions:
            q_filter = models.Filter(must=conditions)

        dense_hits = await self.qdrant.query_points(
            collection_name=collection,
            query=q_vector,
            query_filter=q_filter,
            limit=top_k,
            with_payload=True,
        )
        dense_chunks = [
            Chunk(
                text=hit.payload.get("text", ""),
                doc_id=hit.payload.get("doc_id", ""),
                source=hit.payload.get("source", ""),
                doc_type=hit.payload.get("doc_type", ""),
                section=hit.payload.get("section", ""),
            )
            for hit in dense_hits.points
            if hit.payload
        ]

        # ---- sparse 路：BM25 ----
        sparse_ranked = self.bm25.search(query, top_k=top_k, doc_type=doc_type)
        sparse_chunks = [c for c, _ in sparse_ranked]

        # ---- RRF 融合 ----
        fused = rrf_fusion(dense_chunks, sparse_chunks)
        return [RetrievedChunk(chunk=c, score=s) for c, s in fused]
