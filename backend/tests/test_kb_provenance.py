"""Source metadata must survive corpus loading, storage and model context assembly."""
import json
from pathlib import Path
from types import SimpleNamespace

from app.rag.context import build_context
from app.rag.ingest.corpus import load_corpus
from app.rag.ingest.loader import upsert_chunks
from app.rag.retrievers.hybrid import HybridRetriever, RetrievedChunk
from app.rag.retrievers.sparse_bm25 import BM25Index


def test_corpus_preserves_official_sources_and_legacy_files(tmp_path):
    folder = tmp_path / "regulation"
    folder.mkdir()
    (folder / "付款.txt").write_text("付款规则摘要", encoding="utf-8")
    (folder / "旧资料.txt").write_text("旧资料内容", encoding="utf-8")
    metadata = {"source": "https://www.mee.gov.cn/example.html", "version": "2025修订",
                "effective_date": "2025-06-01", "content_kind": "规则摘要"}
    (tmp_path / "sources.json").write_text(
        json.dumps({"regulation/付款.txt": metadata}), encoding="utf-8",
    )
    docs = {doc["title"]: doc for doc in load_corpus(tmp_path)}
    assert docs["付款"]["source"] == metadata["source"]
    assert docs["付款"]["meta"]["effective_date"] == "2025-06-01"
    assert docs["旧资料"]["meta"] == {}
    assert docs["旧资料"]["source"].startswith("file://")


async def test_provenance_survives_dense_storage_and_sparse_reload(tmp_path, monkeypatch):
    from app.rag.ingest import loader
    from app.rag.ingest.chunker import chunk_document
    from app.rag.retrievers import hybrid

    class FakeClient:
        async def embed(self, texts):
            return [[0.0] * 3 for _ in texts]

    class FakeQdrant:
        points = []

        async def upsert(self, **kwargs):
            self.points = kwargs["points"]

        async def query_points(self, **kwargs):
            return SimpleNamespace(points=self.points)

    monkeypatch.setattr(loader, "get_sf_client", FakeClient)
    monkeypatch.setattr(hybrid, "get_sf_client", FakeClient)
    chunks = chunk_document("付款期限规则摘要", "付款规则", "https://www.mee.gov.cn/rule.html", "regulation")
    chunks[0].meta = {"effective_date": "2025-06-01", "version": "2025修订", "scope": "事业单位与中小企业"}
    qdrant = FakeQdrant()
    await upsert_chunks(qdrant, "test", chunks)
    # 空 sparse 库迫使结果仅经过 dense 路，防止元数据丢失被 sparse 同名结果遮蔽。
    result = await HybridRetriever(qdrant, BM25Index()).retrieve("付款期限", "test")
    assert result[0].chunk.meta == chunks[0].meta
    context = build_context(result)
    assert "doc_id=付款规则" in context
    assert "https://www.mee.gov.cn/rule.html" in context
    assert "2025-06-01" in context and "事业单位与中小企业" in context

    index = BM25Index()
    index.add_chunks(chunks)
    path = tmp_path / "test_bm25.pkl"
    index.save(path)
    reloaded = BM25Index.load(path)
    assert reloaded._chunks[0].meta == chunks[0].meta


def test_context_does_not_mark_legacy_corpus_or_templates_as_verified():
    from app.rag.ingest.chunker import Chunk

    context = build_context([
        RetrievedChunk(Chunk("旧法规", "旧资料", "file:///legacy.txt", "regulation"), 1),
        RetrievedChunk(Chunk("30%预付款", "自建模板", "file:///sample.txt", "template"), 1),
    ])
    assert "版本及现行效力未标注" in context
    assert "自建示例，仅供起草参考" in context


def test_checked_in_manifest_is_covered_by_golden_cases():
    from scripts.check_golden import check_corpus

    root = Path(__file__).resolve().parents[1] / "data" / "kb"
    assert check_corpus(root) == []


async def test_reingest_ids_do_not_depend_on_document_order_or_batch_size(monkeypatch):
    from app.rag.ingest import loader
    from app.rag.ingest.chunker import Chunk

    class FakeClient:
        async def embed(self, texts):
            return [[0.0] * 3 for _ in texts]

    class FakeQdrant:
        def __init__(self):
            self.points = {}

        async def upsert(self, collection_name, points):
            self.points.update({p.id: p for p in points})

    monkeypatch.setattr(loader, "get_sf_client", FakeClient)
    first = Chunk("同一内容", "合同法规", "https://www.mee.gov.cn/a", "regulation", "第一条")
    second = Chunk("第二段", "另一法规", "https://www.mee.gov.cn/b", "regulation", "第二条")
    qdrant = FakeQdrant()
    await upsert_chunks(qdrant, "test", [first, second], batch_size=1)
    original_ids = set(qdrant.points)
    added = Chunk("新增内容", "新法规", "https://www.mee.gov.cn/c", "regulation")
    await upsert_chunks(qdrant, "test", [added, second, first], batch_size=3)
    assert len(qdrant.points) == 3
    assert original_ids <= set(qdrant.points)
    assert loader._point_id(first.doc_id, first.text, "第二条") not in original_ids
