"""已知重大例外不能被模型质检的误放行重新覆盖。"""
import pytest

from app.agent.rules.legal_guards import legal_conclusion_errors, required_legal_findings

EVIDENCE = "第五百九十条：迟延履行后发生不可抗力的，不免除其违约责任。"
FACT = "乙方已迟延交付设备后发生洪水，主张不可抗力免责。"


@pytest.mark.parametrize("clause,advice,evidence,blocked", [
    (FACT, "保留此前责任；仅在实际影响范围内部分或全部免责。", EVIDENCE, True),
    (FACT, "迟延履行后事件不免除责任；不得部分或全部免责。", EVIDENCE, False),
    (FACT, "未迟延的一方确因不可抗力不能履行的，部分或全部免责。", EVIDENCE, False),
    ("因不可抗力不能履行时按实际影响处理。", "按实际影响部分或全部免责。", EVIDENCE, False),
    ("如果乙方已迟延交付后发生洪水，应核实是否属于不可抗力。", "按实际影响部分或全部免责。", EVIDENCE, False),
    ("不免除迟延履行后发生不可抗力时的责任。", "按实际影响部分或全部免责。", EVIDENCE, False),
    (FACT, "仅在实际影响范围内部分或全部免责。", "未展示依据", False),
])
def test_late_performance_guard_requires_explicit_facts_and_visible_rule(clause, advice, evidence, blocked):
    assert bool(legal_conclusion_errors({"suggested_content": advice}, clause, evidence)) is blocked


def test_late_performance_rule_supplies_omitted_safety_finding_once():
    findings = required_legal_findings(FACT, EVIDENCE, [])
    assert len(findings) == 1
    assert "迟延履行后发生不可抗力的，不免除其违约责任" in findings[0]["risk_analysis"]
    assert required_legal_findings(FACT, EVIDENCE, findings) == []


def test_required_finding_needs_explicit_fact_and_visible_rule():
    assert required_legal_findings("发生洪水后可能无法履行", EVIDENCE, []) == []
    assert required_legal_findings(FACT, "未展示依据", []) == []


async def test_bad_repair_cannot_be_streamed_despite_model_approval(monkeypatch):
    from app.agent.nodes import gate

    point = {"original_content": FACT, "risk_analysis": "应保留迟延后例外", "risk_level": "高",
             "suggested_content": "只保留此前责任；仅在实际影响范围内部分或全部免责。"}

    async def approve(*args):
        return True

    async def bad_repair(*args):
        assert "迟延后例外" in args[-1][0]
        return dict(point)

    streamed = []
    monkeypatch.setattr(gate, "_llm_check", approve)
    monkeypatch.setattr(gate, "_retry_fix", bad_repair)
    monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: streamed.append)
    result = await gate.gate_node({"chunks": [FACT], "specialist_outputs": [{
        "chunk_index": 0, "risk_dim": "违约责任与解除", "result": [point], "evidence_context": EVIDENCE,
    }]})
    assert len(result["gated"]) == 1 and "迟延履行后" in result["gated"][0]["risk_analysis"]
    assert result["errors"] and len(streamed) == 1
