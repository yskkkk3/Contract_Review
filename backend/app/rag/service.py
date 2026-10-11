"""RAG service facade: single entry for agent tool calls (search_regulations)."""
import asyncio
import hashlib
from pathlib import Path

from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings
from app.core.qdrant import create_qdrant_client
from app.rag.context import build_context
from app.rag.ingest.loader import ensure_collection
from app.rag.query_expansion import expand_query
from app.rag.rerank import rerank_chunks
from app.rag.retrievers.hybrid import HybridRetriever, RetrievedChunk
from app.rag.retrievers.sparse_bm25 import BM25Index

settings = get_settings()

_COLLECTIONS = (
    settings.qdrant_collection_regulations,
    settings.qdrant_collection_institution,
    settings.qdrant_collection_templates,
)


def _chunk_key(chunk) -> str:
    """与 hybrid.py RRF 融合一致的去重键（doc_id + 文本前缀）。"""
    return hashlib.md5(f"{chunk.doc_id}:{chunk.text[:80]}".encode()).hexdigest()

# 风险维度 → 优先检索的知识库层
DIM_TO_COLLECTION = {
    "主体资格与合规": settings.qdrant_collection_institution,
    "财务与付款": settings.qdrant_collection_institution,
    "知识产权与保密": settings.qdrant_collection_regulations,
    "违约责任与解除": settings.qdrant_collection_regulations,
    "验收交付与质保": settings.qdrant_collection_regulations,
    "争议解决与管辖": settings.qdrant_collection_regulations,
}

DIM_TO_DOC_TYPE = {
    "主体资格与合规": "institution",
    "财务与付款": "institution",
    "知识产权与保密": "regulation",
    "违约责任与解除": "regulation",
    "验收交付与质保": "regulation",
    "争议解决与管辖": "regulation",
}


class RAGService:
    def __init__(
        self,
        qdrant: AsyncQdrantClient | None = None,
        bm25: BM25Index | None = None,
        bm25_path: str | Path | None = None,
    ) -> None:
        self.qdrant = qdrant or create_qdrant_client(timeout=30.0)
        if bm25 is not None:
            self.bm25 = bm25
        elif bm25_path and Path(bm25_path).exists():
            self.bm25 = BM25Index.load(bm25_path)
        else:
            self.bm25 = BM25Index()
        self.retriever = HybridRetriever(self.qdrant, self.bm25)

    async def ensure_ready(self, vector_size: int | None = None) -> None:
        vector_size = vector_size or settings.embedding_dimensions
        for collection in {
            settings.qdrant_collection_regulations,
            settings.qdrant_collection_institution,
            settings.qdrant_collection_templates,
        }:
            await ensure_collection(self.qdrant, collection, vector_size)

    async def search(
        self,
        query: str,
        risk_dim: str | None = None,
        top_k: int = 10,
        doc_type: str | None = None,
    ) -> list[RetrievedChunk]:
        """检索入口：Multi-Query 改写 → 跨三层知识库多路召回 → 合并去重 → rerank。

        Multi-Query（RAG_QUERY_VARIANTS>1 时启用）：LLM 生成同义/子问/术语扩展
        变体，各变体并行走三库混合检索，候选按文档级 key 合并去重后，用原始
        查询做 Cross-encoder 精排——召回覆盖更广，精排语义不失真。

        分层配额：每个文档最多保留 N 个 chunk 进 rerank（防单一文档霸榜），
        终排再做文档级去重（同一文档只保留最高分 chunk，凑满 top_k）——与
        golden set 的文档级标注口径一致，避免同一文档多个 chunk 挤占名额
        导致文档级 Recall 被低估。
        """
        queries = await expand_query(query)
        # 并行执行：变体 × 三层知识库
        tasks = [
            self.retriever.retrieve(
                q, collection, top_k=settings.rag_hybrid_top_k, doc_type=doc_type
            )
            for q in queries
            for collection in _COLLECTIONS
        ]
        results = await asyncio.gather(*tasks)

        # 跨库/跨变体合并，按文档级 key 去重
        candidates: list[RetrievedChunk] = []
        seen: set[str] = set()
        for cands in results:
            for c in cands:
                key = _chunk_key(c.chunk)
                if key not in seen:
                    seen.add(key)
                    candidates.append(c)

        # 分层配额：每文档最多 N 个 chunk 进入精排（控制 rerank 开销 + 防霸榜）
        per_doc: dict[str, list[RetrievedChunk]] = {}
        for c in candidates:
            per_doc.setdefault(c.chunk.doc_id, []).append(c)
        limited: list[RetrievedChunk] = []
        for chunks in per_doc.values():
            chunks.sort(key=lambda x: x.score, reverse=True)
            limited.extend(chunks[: settings.rag_per_doc_quota])

        # 精排用原始查询（改写只服务召回，避免变体语义污染排序）
        reranked = await rerank_chunks(query, limited, top_k=top_k * 3)
        # 终排文档级去重：同一文档只保留最高分 chunk，凑满 top_k
        final: list[RetrievedChunk] = []
        seen_docs: set[str] = set()
        for c in reranked:
            if c.chunk.doc_id not in seen_docs:
                seen_docs.add(c.chunk.doc_id)
                final.append(c)
            if len(final) >= top_k:
                break
        return final

    async def search_with_context(
        self,
        query: str,
        risk_dim: str | None = None,
        top_k: int = 5,
    ) -> tuple[str, list[RetrievedChunk]]:
        evidence = await self.search(query, risk_dim=risk_dim, top_k=top_k)
        return build_context(evidence), evidence

    async def close(self) -> None:
        await self.qdrant.close()


_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        bm25_path = settings.kb_bm25_path or str(
            Path(settings.oss_bucket_dir).parent / "kb_bm25.pkl"
        )
        _rag_service = RAGService(bm25_path=bm25_path)
    return _rag_service
