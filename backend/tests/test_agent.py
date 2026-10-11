"""Agent pure-logic tests: clause split, rule fallback, routing, gate, arbitration."""

from app.agent.nodes.arbitration import _arbitrate_rules, _overall_risk
from app.agent.nodes.gate import _rule_check
from app.agent.nodes.intent import _rule_classify
from app.agent.nodes.router import _rule_route
from app.agent.prompts import load_prompt, load_risk_dim_prompt
from app.agent.state import RISK_DIMS
from app.services.review_service import split_contract_clauses


def test_split_clauses_by_section():
    text = "第一条 总则\n这是第一条内容。\n第二条 验收\n验收标准应明确。"
    chunks = split_contract_clauses(text)
    assert len(chunks) == 2
    assert "第一条" in chunks[0]
    assert "第二条" in chunks[1]


def test_split_long_chunk():
    text = "第三条 付款\n" + "付款条款内容。" * 300
    chunks = split_contract_clauses(text, max_chars=200)
    assert len(chunks) > 2


def test_rule_intent_fallback():
    intent, conf = _rule_classify("请审阅这份合同的风险点")
    assert intent == "review"
    intent, _ = _rule_classify("帮我比对两份合同")
    assert intent == "compare"
    intent, _ = _rule_classify("合同类型怎么配置")
    assert intent == "admin"
    intent, _ = _rule_classify("随便聊聊")
    assert intent == "chat"


def test_rule_route_dimensions():
    dims = _rule_route("乙方逾期付款应按合同总金额的万分之五支付违约金")
    assert "财务与付款" in dims
    assert "违约责任与解除" in dims
    # 无关键词 → 兜底维度
    assert _rule_route("关于本合同的签署说明") == ["主体资格与合规"]


def test_gate_rule_check():
    ok = {"original_content": "条款", "risk_analysis": "分析", "risk_level": "高", "suggested_content": "建议"}
    assert _rule_check(ok) == []
    bad = {"original_content": "", "risk_analysis": "", "risk_level": "超高", "suggested_content": ""}
    assert len(_rule_check(bad)) >= 3


def test_arbitration_merge_and_sort():
    points = [
        {"chunk_index": 2, "original_content": "B", "risk_analysis": "a1", "risk_level": "中",
         "suggested_content": "s1", "risk_dim": "财务与付款"},
        {"chunk_index": 1, "original_content": "A", "risk_analysis": "a0", "risk_level": "高",
         "suggested_content": "s0", "risk_dim": "验收交付与质保"},
        {"chunk_index": 1, "original_content": "A", "risk_analysis": "a1b", "risk_level": "低",
         "suggested_content": "s1b", "risk_dim": "违约责任与解除"},
    ]
    merged = _arbitrate_rules(points)
    assert [p["index"] for p in merged] == [1, 2]  # 按序
    assert merged[0]["dim_count"] == 2
    assert merged[0]["risk_level"] == "高"  # 取最高等级


def test_overall_risk():
    low = [{"risk_level": "低"}] * 3
    assert _overall_risk(low) == "低"
    mid = [{"risk_level": "中"}] * 6
    assert _overall_risk(mid) == "中"
    high = [{"risk_level": "高"}] * 4
    assert _overall_risk(high) == "高"


def test_risk_dims_complete():
    assert len(RISK_DIMS) == 6
    for dim in RISK_DIMS:
        assert load_risk_dim_prompt(dim).strip(), f"missing prompt: {dim}"


def test_prompt_loader_interpolation():
    text = load_prompt("specialist_base", risk_dim="财务与付款", stance="甲方", intensity="严格")
    assert "财务与付款" in text
    assert "甲方" in text
    assert "严格" in text
