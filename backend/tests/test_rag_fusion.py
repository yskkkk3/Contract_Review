"""Ranking regressions: cross-query evidence, collection isolation and embedding reuse."""
from types import SimpleNamespace

import pytest

from app.rag.ingest.chunker import Chunk
from app.rag.retrievers.hybrid import HybridRetriever, RetrievedChunk, chunk_key, fuse_rankings
from app.rag.retrievers.sparse_bm25 import BM25Index


def test_fusion_accumulates_support_across_queries_without_duplicate_votes():
    first = Chunk("仅原查询命中", "A", "source", "regulation")
    supported = Chunk("三个变体都能找到", "B", "source", "regulation")
    fused = fuse_rankings([[first, supported], [supported], [supported, supported]])
    assert fused[0][0] == supported
    assert fused[0][1] == pytest.approx(1 / 62 + 2 / 61)


def test_matching_prefix_does_not_discard_different_legal_conditions():
    prefix = "通用条文开头" * 20
    exception = Chunk(prefix + "但双方另有约定的除外", "文件", "source", "regulation", "第一条")
    obligation = Chunk(prefix + "不得通过约定排除该项义务", "文件", "source", "regulation", "第一条")
    assert chunk_key(exception) != chunk_key(obligation)
    assert len(fuse_rankings([[exception], [obligation]])) == 2


async def test_dense_and_sparse_obey_same_collection_and_source_filters(monkeypatch):
    from app.rag.retrievers import hybrid

    index = BM25Index()
    index.add_chunks([
        Chunk("验收付款规则", "制度甲", "allowed", "institution"),
        Chunk("验收付款规则", "制度乙", "other", "institution"),
        Chunk("验收付款规则", "模板", "allowed", "template"),
        Chunk("无关的法律知识", "法规", "source", "regulation"),
        Chunk("科研项目申报办法", "制度丙", "other", "institution"),
    ])
    sent = {}

    class Qdrant:
        async def query_points(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(points=[])

    class Client:
        async def embed(self, *args):
            raise AssertionError("Caller already supplied the query vector")

    monkeypatch.setattr(hybrid, "get_sf_client", Client)
    retriever = HybridRetriever(Qdrant(), index)
    hits = await retriever.retrieve("验收付款规则", hybrid.settings.qdrant_collection_institution,
                                    filters={"source": "allowed"}, query_vector=[0.1, 0.2])
    assert [hit.chunk.doc_id for hit in hits] == ["制度甲"]
    conditions = sent["query_filter"].must
    assert {(condition.key, condition.match.value) for condition in conditions} == {
        ("doc_type", "institution"), ("source", "allowed"),
    }
    assert sent["query"] == [0.1, 0.2]


async def test_search_reuses_embeddings_and_retains_cross_query_support(monkeypatch):
    from app.rag import service

    embedded = []
    calls = []
    limited = []
    first = Chunk("首次命中段落", "法规", "source", "regulation")
    preferred = Chunk("跨查询共同命中的更相关段落", "法规", "source", "regulation")

    class Client:
        async def embed(self, queries):
            embedded.append(queries)
            return [[0.1], [0.2]]

    async def queries(query):
        return [query, "改写"]

    class Retriever:
        async def retrieve(self, query, collection, **kwargs):
            calls.append((query, collection, kwargs["query_vector"]))
            if collection != service.settings.qdrant_collection_regulations:
                return []
            chunks = [first, preferred] if query == "原查询" else [preferred]
            return [RetrievedChunk(chunk, 1) for chunk in chunks]

    async def rerank(query, candidates, **kwargs):
        limited.extend(candidates)
        return candidates

    monkeypatch.setattr(service, "get_sf_client", Client)
    monkeypatch.setattr(service, "expand_query", queries)
    monkeypatch.setattr(service, "rerank_chunks", rerank)
    monkeypatch.setattr(service.settings, "rag_per_doc_quota", 1)
    rag = service.RAGService(qdrant=object(), bm25=BM25Index())
    rag.retriever = Retriever()
    hits = await rag.search("原查询", top_k=5)
    assert embedded == [["原查询", "改写"]]
    assert len(calls) == 6
    assert all(vector == ([0.1] if query == "原查询" else [0.2]) for query, _, vector in calls)
    assert [candidate.chunk for candidate in limited] == [preferred]
    assert hits[0].chunk.text == preferred.text


async def test_query_variant_cache_respects_requested_count_and_can_be_disabled(monkeypatch):
    from app.rag import query_expansion

    calls = []

    class Client:
        async def chat(self, *args, **kwargs):
            calls.append(kwargs)
            return '["查询甲", "查询乙"]'

    monkeypatch.setattr(query_expansion, "get_sf_client", Client)
    monkeypatch.setattr(query_expansion, "_cache", query_expansion._TTLCache())
    assert await query_expansion.expand_query("原问题", variants=3) == ["原问题", "查询甲", "查询乙"]
    assert await query_expansion.expand_query("原问题", variants=2) == ["原问题", "查询甲"]
    assert await query_expansion.expand_query("原问题", variants=3) == ["原问题", "查询甲", "查询乙"]
    assert await query_expansion.expand_query("原问题", variants=0) == ["原问题"]
    assert len(calls) == 2
    assert all(call["brief"] for call in calls)
