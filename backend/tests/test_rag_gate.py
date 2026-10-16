"""Metric gate must consume the actual evaluator's keys and enforce each threshold."""
import asyncio
import json
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


async def test_gate_limits_concurrency_and_saves_the_actual_results(monkeypatch, tmp_path):
    from scripts import gate_metrics

    class FakeRag:
        active = 0
        peak = 0
        closed = False

        async def ensure_ready(self):
            pass

        async def search(self, *args, **kwargs):
            self.active += 1
            self.peak = max(self.peak, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return [SimpleNamespace(chunk=SimpleNamespace(doc_id="相关文档"))]

        async def close(self):
            self.closed = True

    rag = FakeRag()
    monkeypatch.setattr(gate_metrics, "get_rag_service", lambda: rag)
    monkeypatch.setattr(gate_metrics, "GOLDEN_SET", [
        SimpleNamespace(id=f"T{i}", question=f"问题{i}", risk_dim="财务与付款", relevant_docs=["相关文档"])
        for i in range(4)
    ])
    output = tmp_path / "report.json"
    assert await gate_metrics.run(0.6, 0.4, 0.5, concurrency=2, output=output) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["case_count"] == 4 and report["gate_exit_code"] == 0
    assert report["metrics"]["recall@k"] == 1
    assert [row["id"] for row in report["detail"]] == ["T0", "T1", "T2", "T3"]
    assert rag.closed and rag.peak == 2


async def test_gate_closes_client_when_retrieval_fails(monkeypatch):
    from scripts import gate_metrics

    class FakeRag:
        closed = False

        async def ensure_ready(self):
            pass

        async def search(self, *args, **kwargs):
            raise RuntimeError("retrieval unavailable")

        async def close(self):
            self.closed = True

    rag = FakeRag()
    monkeypatch.setattr(gate_metrics, "get_rag_service", lambda: rag)
    monkeypatch.setattr(gate_metrics, "GOLDEN_SET", [
        SimpleNamespace(question="问题", risk_dim="财务与付款", relevant_docs=["相关文档"]),
    ])
    with pytest.raises(ExceptionGroup):
        await gate_metrics.run(0.6, 0.4, 0.5)
    assert rag.closed


async def test_interrupted_gate_preserves_checkpoints_without_publishing_partial_metrics(monkeypatch, tmp_path):
    import httpx

    from scripts import gate_metrics

    class FakeRag:
        closed = False
        calls = 0

        async def ensure_ready(self):
            pass

        async def search(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 2:
                response = httpx.Response(400, json={"code": "Arrearage"},
                                          request=httpx.Request("POST", "https://example.org/reranks"))
                raise httpx.HTTPStatusError("billing unavailable", request=response.request, response=response)
            return [SimpleNamespace(chunk=SimpleNamespace(doc_id="相关"))]

        async def close(self):
            self.closed = True

    rag = FakeRag()
    monkeypatch.setattr(gate_metrics, "get_rag_service", lambda: rag)
    monkeypatch.setattr(gate_metrics, "GOLDEN_SET", [
        SimpleNamespace(id=f"T{i}", question=f"问题{i}", risk_dim="财务与付款", relevant_docs=["相关"])
        for i in range(2)
    ])
    output = tmp_path / "interrupted.json"
    with pytest.raises(ExceptionGroup):
        await gate_metrics.run(0.6, 0.4, 0.5, concurrency=1, output=output)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["evaluation_status"] == "incomplete"
    assert report["metrics"] is None and report["gate_exit_code"] == 1
    assert report["case_count"] == 1 and report["expected_case_count"] == 2
    assert report["detail"][1]["provider_error_code"] == "Arrearage"
    assert len(list(output.with_suffix(".cases").glob("*.json"))) == 2
    assert rag.closed
