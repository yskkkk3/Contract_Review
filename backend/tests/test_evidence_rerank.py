"""Evidence ordering must never invent candidates or lose the deterministic fallback."""
import asyncio
import json

import pytest

from app.rag import rerank
from app.rag.ingest.chunker import Chunk
from app.rag.retrievers.hybrid import RetrievedChunk


@pytest.mark.parametrize("indices", [[0, 0], [0, 9], [True, 1], [0, "1"], [0], []])
def test_ranking_rejects_invalid_or_incomplete_indices(indices):
    assert rerank._ranking_indices({"ranked_indices": indices}, count=3, required=2) is None


async def test_evidence_ranking_groups_passages_and_maps_valid_indices(monkeypatch):
    received = {}
    chunks = [
        RetrievedChunk(Chunk("付款条文", "法规甲", "source", "regulation"), 0.9),
        RetrievedChunk(Chunk("付款起算例外", "法规甲", "source", "regulation"), 0.8),
        RetrievedChunk(Chunk("学校验收制度", "制度乙", "source", "institution"), 0.7),
    ]

    class Client:
        async def chat(self, messages, **kwargs):
            received.update(json.loads(messages[1]["content"]))
            assert kwargs["brief"] is True
            return '{"ranked_indices":[1,0]}'

    monkeypatch.setattr(rerank, "get_sf_client", Client)
    hits = await rerank.rerank_evidence("验收与付款", chunks, top_k=2)
    assert [item.chunk.doc_id for item in hits] == ["制度乙", "法规甲"]
    assert received["documents"][0]["passages"] == ["付款条文", "付款起算例外"]
    assert len(received["documents"]) == 2


@pytest.mark.parametrize("failure", ["invalid", "exception", "timeout"])
async def test_failed_evidence_ranking_keeps_cross_encoder_order(monkeypatch, failure):
    chunks = [RetrievedChunk(Chunk(text, text, "source", "regulation"), score)
              for text, score in [("真实甲", 0.9), ("真实乙", 0.8)]]

    class Client:
        async def chat(self, *args, **kwargs):
            if failure == "exception":
                raise RuntimeError("unavailable")
            if failure == "timeout":
                await asyncio.sleep(1)
            return '{"ranked_indices":[0,999]}'

    monkeypatch.setattr(rerank, "get_sf_client", Client)
    monkeypatch.setattr(rerank.settings, "rag_evidence_rerank_timeout", 0.01)
    assert await rerank.rerank_evidence("问题", chunks, top_k=2) == chunks


async def test_disabled_evidence_ranking_does_not_call_llm(monkeypatch):
    monkeypatch.setattr(rerank.settings, "rag_evidence_rerank_enabled", False)
    chunks = [RetrievedChunk(Chunk("原文", "A", "source", "regulation"), 1)]
    monkeypatch.setattr(rerank, "get_sf_client", lambda: pytest.fail("Should not call model"))
    assert await rerank.rerank_evidence("问题", chunks, top_k=5) == chunks
