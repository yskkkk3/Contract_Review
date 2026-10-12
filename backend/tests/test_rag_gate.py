"""Metric gate must consume the actual evaluator's keys and enforce each threshold."""
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    ("recall", "rank", "ndcg", "expected"),
    [(0.4, 0.4, 0.3, 0), (0.6, 0.4, 0.3, 1), (0.4, 0.6, 0.3, 1), (0.4, 0.4, 0.5, 1)],
)
async def test_gate_consumes_real_metrics_and_enforces_thresholds(monkeypatch, recall, rank, ndcg, expected):
    from scripts import gate_metrics

    class FakeRag:
        closed = False

        async def ensure_ready(self):
            pass

        async def search(self, *args, **kwargs):
            return [SimpleNamespace(chunk=SimpleNamespace(doc_id=doc_id)) for doc_id in ("无关", "相关A")]

        async def close(self):
            self.closed = True

    rag = FakeRag()
    monkeypatch.setattr(gate_metrics, "get_rag_service", lambda: rag)
    monkeypatch.setattr(gate_metrics, "GOLDEN_SET", [
        SimpleNamespace(question="验收", risk_dim="验收交付与质保", relevant_docs=["相关A", "相关B"]),
    ])
    assert await gate_metrics.run(recall, rank, ndcg) == expected
    assert rag.closed
