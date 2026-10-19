"""关键规则的正文、版本、例外及实际展示须一起核验。"""
from pathlib import Path
from types import SimpleNamespace

from app.rag.context import assemble_context
from app.rag.ingest.chunker import Chunk, chunk_document
from app.rag.ingest.corpus import load_corpus
from app.rag.legal_coverage import (
    check_coverage,
    legal_context,
    legal_profiles,
    supplemental_evidence,
)
from app.rag.retrievers.hybrid import RetrievedChunk
from app.rag.retrievers.sparse_bm25 import BM25Index


def corpus_index():
    index = BM25Index()
    chunks = []
    for doc in load_corpus(Path(__file__).resolve().parents[1] / "data/kb"):
        parts = chunk_document(doc["text"], doc["title"], doc["source"], doc["doc_type"])
        for part in parts:
            part.meta.update(doc["meta"])
        chunks.extend(parts)
    index.add_chunks(chunks)
    return index


def test_all_curated_rules_and_exceptions_have_verified_corpus_witnesses():
    profiles = legal_profiles()
    result = check_coverage(profiles, supplemental_evidence(profiles, corpus_index()))
    assert len(result.facets) >= 30
    assert result.missing == []


def test_clause_examples_deliver_each_required_document_and_conditions():
    from app.rag.eval.critical_cases import CRITICAL_CASES

    index = corpus_index()
    for case in CRITICAL_CASES:
        result = legal_context(case.clause, case.risk_dim, index)
        visible = {item.chunk.doc_id for item in result.evidence}
        assert set(case.required_docs) <= visible, case.id
        assert not result.coverage.missing, (case.id, result.coverage.missing)
        assert len(result.text) <= 7000


def test_missing_or_unverified_corpus_is_never_replaced_by_checklist_text():
    index = BM25Index()
    result = legal_context("学校委托软件开发，付费后著作权当然归学校", "知识产权与保密", index)
    assert result.evidence == [] and result.coverage.missing
    assert "依据未完整展示" in result.text
    index.add_chunks([Chunk("第11条，书面合同未明确约定时受托人享有；已明确约定依约处理",
                            "计算机软件保护条例·委托开发与许可边界", "legacy", "regulation")])
    assert legal_context("委托软件开发", "知识产权与保密", index).coverage.missing


def test_budget_skips_oversized_block_and_never_cites_it_as_visible():
    large = RetrievedChunk(Chunk("大" * 2000, "太长", "source", "regulation"), 1)
    small = RetrievedChunk(Chunk("规则及例外均在此", "可展示", "source", "regulation"), 0.5)
    context = assemble_context([large, small], max_chars=300)
    assert [e.chunk.doc_id for e in context.visible] == ["可展示"]
    assert context.omitted == ["太长"]
    assert len(context.text) <= 300
    only_large = assemble_context([large], max_chars=300)
    assert "未完成依据核验" in only_large.text
    assert "未检索到" not in only_large.text


async def test_valid_empty_specialist_answer_does_not_retry_until_it_invents_a_risk(monkeypatch):
    import asyncio

    from app.agent.nodes import specialist

    async def tools(*args, **kwargs):
        return '{"risk_points": []}', []

    monkeypatch.setattr(specialist, "get_sf_client", lambda: object())
    monkeypatch.setattr(specialist, "call_llm_with_tools", tools)
    result = await specialist._run_specialist(
        asyncio.Semaphore(1), "正常条款", "财务与付款",
        {"stance": "甲方", "intensity": "标准", "chunks": ["正常条款", "正常条款"]}, None,
        chunk_index=1,
    )
    assert result["result"] == [] and result["diagnostics"] == []
    assert result["chunk_index"] == 1


async def test_gate_receives_real_evidence_and_fails_closed_when_check_unavailable(monkeypatch):
    from app.agent.nodes import gate

    captured = {}

    class Client:
        async def chat_structured(self, messages, **kwargs):
            import json

            captured.update(json.loads(messages[1]["content"]))
            return {"valid": True}

    monkeypatch.setattr(gate, "get_sf_client", Client)
    assert await gate._llm_check({"risk_analysis": "待核验"}, "源条款", "实际正文与例外")
    assert captured["evidence_context"] == "实际正文与例外"
    assert captured["accepted_risk_points"] == []

    class Unavailable:
        async def chat_structured(self, *args, **kwargs):
            raise RuntimeError("unavailable")

    monkeypatch.setattr(gate, "get_sf_client", Unavailable)
    assert await gate._llm_check({}, "源条款", "正文") is False


def test_failed_judge_requires_valid_grounded_appeal_to_pass():
    from scripts.eval_critical import _judge_passed, _valid_judge

    failed = {"passed": False, "missed": ["遗漏"], "unsupported": [],
              "explanation": "首轮失败"}
    overturned = {"passed": True, "missed": [], "unsupported": [],
                  "explanation": "原文已有对应内容，撤销首轮判断"}
    malformed = {"passed": True, "missed": "", "unsupported": [], "explanation": ""}
    inconsistent = {"passed": False, "missed": ["该项不能成立"], "unsupported": [],
                    "explanation": "全部缺陷均撤销，未发现其他实质缺陷，改为通过"}
    inconsistent_appeal = {
        "passed": False,
        "missed": [],
        "unsupported": ["首轮缺陷不能成立"],
        "explanation": "首轮两项均不能成立，故撤销全部缺陷，改判通过。",
    }
    assert _valid_judge(failed) and not _judge_passed(failed)
    assert _valid_judge(overturned) and _judge_passed(overturned)
    assert not _valid_judge(malformed) and not _judge_passed(malformed)
    assert not _valid_judge(inconsistent) and not _judge_passed(inconsistent)
    assert not _valid_judge(inconsistent_appeal) and not _judge_passed(inconsistent_appeal)


def test_critical_judge_prompt_preserves_software_specific_modification_rule():
    from app.agent.prompts import load_prompt

    prompt = load_prompt("eval_critical")
    assert "计算机软件条例" in prompt
    assert "不得机械套用普通作品修改权规则" in prompt


def test_one_confirmed_high_risk_is_not_summarized_as_low():
    from app.agent.nodes.arbitration import _overall_risk

    assert _overall_risk([{"risk_level": "高"}]) == "高"
    assert _overall_risk([{"risk_level": "中"}]) == "中"
    assert _overall_risk([{"risk_level": "低"}] * 20) == "低"


async def test_tool_reasoning_is_preserved_for_provider_followup():
    from app.agent.tools.executor import call_llm_with_tools
    from app.agent.tools.registry import default_tools

    call = SimpleNamespace(id="a", function=SimpleNamespace(name="calc_penalty", arguments='{"amount":1,"rate":1,"days":1}'))

    class Client:
        calls = 0

        async def chat_with_tools(self, messages, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(content="", tool_calls=[call], reasoning_content="provider-required-data")
            assert messages[-2]["reasoning_content"] == "provider-required-data"
            return SimpleNamespace(content="done", tool_calls=[])

    result, _ = await call_llm_with_tools(Client(), [], default_tools(), model="fake")
    assert result == "done"


async def test_completeness_audit_catches_omission_in_empty_draft_without_answer_leak(monkeypatch):
    import asyncio
    import json

    from app.agent.nodes import specialist
    from app.rag.service import RAGService

    clause = "学校委托乙方开发软件，无约定时学校主张著作权当然归学校。"
    rag = object.__new__(RAGService)
    rag.bm25 = corpus_index()

    async def tools(*args, **kwargs):
        return '{"risk_points": []}', []

    class Client:
        async def chat_structured(self, messages, **kwargs):
            payload = json.loads(messages[1]["content"])
            assert payload["draft"] == []
            assert "第11条" in payload["evidence_context"]
            assert "expected" not in payload and "prohibited" not in payload
            return {"status": "revised", "unresolved": [], "risk_points": [{
                "original_content": clause, "risk_analysis": "未约定时并不当然归学校",
                "risk_level": "高", "suggested_content": "以书面合同明确权属",
                "evidence_refs": ["计算机软件保护条例·委托开发与许可边界", "虚构文件"],
            }]}

    monkeypatch.setattr(specialist, "get_sf_client", Client)
    monkeypatch.setattr(specialist, "call_llm_with_tools", tools)
    monkeypatch.setattr(specialist.settings, "agent_evidence_audit_enabled", True)
    result = await specialist._run_specialist(
        asyncio.Semaphore(1), clause, "知识产权与保密",
        {"stance": "甲方", "intensity": "标准", "chunks": [clause]}, rag,
    )
    assert result["initial_result"] == [] and result["audit_status"] == "revised"
    assert len(result["result"]) == 1
    assert result["result"][0]["evidence_refs"] == ["计算机软件保护条例·委托开发与许可边界"]


async def test_successful_completeness_recovery_clears_transient_specialist_error(monkeypatch):
    import asyncio

    from app.agent.nodes import specialist
    from app.rag.service import RAGService

    clause = "学校委托乙方开发软件，无约定时学校主张著作权当然归学校。"
    rag = object.__new__(RAGService)
    rag.bm25 = corpus_index()

    async def failed_tools(*args, **kwargs):
        raise RuntimeError("transient upstream failure")

    class Client:
        async def chat_structured(self, *args, **kwargs):
            return {"status": "revised", "unresolved": [], "risk_points": [{
                "original_content": clause, "risk_analysis": "未约定时不当然归学校",
                "risk_level": "高", "suggested_content": "书面明确权属",
                "evidence_refs": ["计算机软件保护条例·委托开发与许可边界"],
            }]}

    monkeypatch.setattr(specialist, "get_sf_client", Client)
    monkeypatch.setattr(specialist, "call_llm_with_tools", failed_tools)
    monkeypatch.setattr(specialist.settings, "agent_evidence_audit_enabled", True)
    result = await specialist._run_specialist(
        asyncio.Semaphore(1), clause, "知识产权与保密",
        {"stance": "甲方", "intensity": "标准", "chunks": [clause]}, rag,
    )
    assert result["audit_status"] == "revised"
    assert len(result["result"]) == 1
    assert result["diagnostics"] == []


def test_conditionable_sensitive_review_is_not_blocked_by_followup_materials():
    from app.agent.nodes.specialist import _can_complete_with_conditioned_finding

    clause = (
        "校园平台处理健康类敏感个人信息，已提供具体法律依据证明属于履行法定职责所必需，"
        "非基于同意；仍实施必要性审查、安全措施和影响评估。"
    )
    evidence = (
        "个人信息保护法·敏感信息与影响评估：敏感个人信息须有特定目的和充分必要性；"
        "处理前进行个人信息保护影响评估并留存记录。"
    )
    assert _can_complete_with_conditioned_finding(clause, evidence, [], [])
    assert not _can_complete_with_conditioned_finding(
        clause, evidence, [], ["缺少敏感信息规则正文"],
    )


async def test_gate_rejects_missing_verdict_and_never_streams_rejected_result(monkeypatch):
    from app.agent.nodes import gate

    class Invalid:
        async def chat_structured(self, *args, **kwargs):
            return {"explanation": "missing verdict"}

    monkeypatch.setattr(gate, "get_sf_client", Invalid)
    assert not await gate._llm_check({}, "条款", "依据")

    async def no_fix(*args, **kwargs):
        return None

    streamed = []
    monkeypatch.setattr(gate, "_retry_fix", no_fix)
    monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: streamed.append)
    result = await gate.gate_node({
        "chunks": ["原文"], "errors": [], "specialist_outputs": [{
            "chunk_index": 0, "risk_dim": "财务与付款", "result": [{
                "original_content": "原文", "risk_analysis": "未经证据支持的结论",
                "risk_level": "高", "suggested_content": "修改",
            }],
        }],
    })
    assert result["gated"] == [] and result["errors"] and streamed == []


async def test_arbitration_preserves_each_material_repair_and_warns_on_incomplete_review(monkeypatch):
    from app.agent.nodes import arbitration

    points = [{"chunk_index": 0, "risk_dim": "财务与付款", "original_content": "付款",
               "risk_analysis": "账期风险", "risk_level": "高", "suggested_content": "限制账期"},
              {"chunk_index": 0, "risk_dim": "财务与付款", "original_content": "保证金",
               "risk_analysis": "现金唯一限制", "risk_level": "中", "suggested_content": "允许非现金担保"}]
    merged = arbitration._arbitrate_rules(points, ["付款和保证金"])
    assert "限制账期" in merged[0]["suggested_content"]
    assert "允许非现金担保" in merged[0]["suggested_content"]
    assert merged[0]["original_content"] == "付款和保证金"

    async def summary(*args):
        return {"summary": "没有风险", "suggestion": "直接签订", "overall_risk": "低"}

    monkeypatch.setattr(arbitration, "_llm_summary", summary)
    result = await arbitration.arbitration_node({"gated": [], "stance": "甲方", "errors": ["核验失败"]})
    assert "尚未形成完整审阅结论" in result["summary"]["summary"]
    assert "请先补查" in result["summary"]["suggestion"]
    assert "直接签订" not in result["summary"]["suggestion"].replace("不能支持直接签订", "")
    assert result["summary"]["review_status"] == "incomplete"


async def test_reingest_removes_corrected_document_old_law_but_preserves_other_documents(monkeypatch):
    from qdrant_client import AsyncQdrantClient, models

    from app.rag.ingest import loader

    class Client:
        async def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(loader, "get_sf_client", Client)
    qdrant = AsyncQdrantClient(":memory:")
    try:
        await qdrant.create_collection("test", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
        await loader.upsert_chunks(qdrant, "test", [
            Chunk("错误旧条号", "需纠正文档", "legacy", "regulation"),
            Chunk("其他用户文档", "保持原样", "user", "regulation"),
        ])
        await loader.replace_document_chunks(qdrant, "test", [
            Chunk("已核对新条号", "需纠正文档", "official", "regulation"),
        ])
        points, _ = await qdrant.scroll("test", limit=10)
        assert {point.payload["text"] for point in points} == {"已核对新条号", "其他用户文档"}
    finally:
        await qdrant.close()


async def test_failed_reingest_does_not_delete_previous_evidence(monkeypatch):
    import pytest

    from app.rag.ingest import loader

    class FailedClient:
        async def embed(self, texts):
            raise RuntimeError("embedding unavailable")

    class Store:
        async def delete(self, **kwargs):
            raise AssertionError("must preserve previous evidence on failed write")

    monkeypatch.setattr(loader, "get_sf_client", FailedClient)
    with pytest.raises(RuntimeError, match="embedding unavailable"):
        await loader.replace_document_chunks(Store(), "test", [Chunk("corrected", "doc", "source", "regulation")])
