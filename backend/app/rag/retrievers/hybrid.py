"""Hybrid retriever: dense (Qdrant + bge-m3) + sparse (BM25) -> RRF fusion.

简历点：双路召回互补（语义泛化 + 关键词精确），RRF 融合避免异构分数
直接相加的尺度问题，再由 Cross-encoder 精排提精度。
"""
import hashlib
import json
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


def chunk_key(chunk: Chunk) -> str:
    """完整内容与章节共同标识条文，不能只比较相同的开头。"""
    identity = json.dumps([chunk.doc_id, chunk.section, chunk.text], ensure_ascii=False)
    return hashlib.sha256(identity.encode()).hexdigest()


def fuse_rankings(rankings: list[list[Chunk]], k: int = 60) -> list[tuple[Chunk, float]]:
    """按排名融合任意多路召回；每一路同一条文最多贡献一次。"""
    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for rank, chunk in enumerate(ranking, start=1):
            key = chunk_key(chunk)
            if key in seen:
                continue
            seen.add(key)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            chunks[key] = chunk
    return [(chunks[key], score) for key, score in
            sorted(scores.items(), key=lambda item: item[1], reverse=True)]


def rrf_fusion(
    dense_ranked: list[Chunk],
    sparse_ranked: list[Chunk],
    k: int = 60,
) -> list[tuple[Chunk, float]]:
    """Reciprocal Rank Fusion：score = Σ 1/(k + rank)。"""
    return fuse_rankings([dense_ranked, sparse_ranked], k=k)


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
        query_vector: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        """双路召回 → RRF 融合 → 返回按融合分排序的 chunks。"""
        # ---- dense 路：Qdrant 向量检索 ----
        q_vector = query_vector if query_vector is not None else (await get_sf_client().embed([query]))[0]
        collection_types = {
            settings.qdrant_collection_regulations: "regulation",
            settings.qdrant_collection_institution: "institution",
            settings.qdrant_collection_templates: "template",
        }
        collection_type = collection_types.get(collection)
        if doc_type and collection_type and doc_type != collection_type:
            return []
        doc_type = doc_type or collection_type
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
                meta=hit.payload.get("meta", {}),
            )
            for hit in dense_hits.points
            if hit.payload
        ]

        # ---- sparse 路：BM25 ----
        sparse_ranked = self.bm25.search(query, top_k=top_k, doc_type=doc_type, filters=filters)
        sparse_chunks = [c for c, _ in sparse_ranked]

        # ---- RRF 融合 ----
        fused = rrf_fusion(dense_chunks, sparse_chunks)
        return [RetrievedChunk(chunk=c, score=s) for c, s in fused]
