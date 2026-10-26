"""Step 4: business-specific directions, sufficient clauses and missing-material guards.

These tests exercise orchestration using a fake reviewer, not legal/model accuracy.
"""
import asyncio
import json

import pytest

from app.agent.nodes.specialist import _check_results, _run_specialist
from app.agent.prompts import load_prompt
from app.agent.review_profiles import PROFILES, assessed_scope, profile_scope


@pytest.mark.parametrize("failure", ["upstream", "truncated"])
async def test_failed_generation_does_not_start_another_paid_completeness_pass(monkeypatch, failure):
    from types import SimpleNamespace

    from app.agent.nodes import specialist
    from app.rag.client import LLMOutputTruncated
    from app.rag.service import RAGService

    class ProviderError(Exception):
        status_code = 502

    async def fail(*_args, **_kwargs):
        raise ProviderError() if failure == "upstream" else LLMOutputTruncated("output incomplete")

    class NoAuditClient:
        async def chat_structured(self, *_args, **_kwargs):
            pytest.fail("A transport/truncation failure must not trigger another completeness request")

    rag = object.__new__(RAGService)
    bundle = SimpleNamespace(text="verified evidence", evidence=[],
                             coverage=SimpleNamespace(facets={"required": True}, missing=[]))
    monkeypatch.setattr(rag, "legal_supplement", lambda *_args, **_kwargs: bundle)
    monkeypatch.setattr(specialist, "call_llm_with_tools", fail)
    monkeypatch.setattr(specialist, "get_sf_client", lambda: NoAuditClient())
    text = "约定交付定制源代码及部署文档。"
    output = await _run_specialist(asyncio.Semaphore(1), text, "验收交付与质保",
                                  {"contract_type": "信息化项目", "stance": "甲方", "intensity": "标准", "chunks": [text]},
                                  rag, 0, True)
    assert output["result"] == []
    assert output["audit_status"] == "not_run"
    assert output["diagnostics"]
    assert output["provider_unavailable"] is (failure == "upstream")

CASES = (
    ("货物采购", "warranty", "质保期及退换方式由乙方另行通知。", "质保及退换按附件清单执行，维修费用承担已列明。"),
    ("工程建设", "changes", "变更签证和新增工程量的结算价格以后再议。", "设计变更须书面确认工程量，结算按双方约定计价方法执行。"),
    ("信息化项目", "deliverables", "仅交付线上账号，不提供部署资料，源代码交付另议。", "定制源代码、部署文档、接口与测试资料均按附件交付验收。"),
    ("运维与维保", "sla", "故障修复及响应时间由服务方决定。", "故障分级、响应和恢复目标、例外及统计口径均见附件。"),
    ("物业与餐饮", "scope", "保洁范围和巡查频次由服务方自行安排。", "保洁区域、频次与质量标准均列入附件服务清单。"),
    ("租赁服务", "costs", "押金扣除标准及租金递增另行协商。", "租金、押金扣除条件及退租后的结算安排已明确列明。"),
    ("咨询与评估", "deliverables", "成果形式和咨询范围由乙方日后确定。", "咨询范围、成果形式、研究方法和交付标准均见成果清单。"),
    ("检验与检测", "samples", "样品流转不留记录，送样结论视为全部产品合格。", "送样检测的样品流转与留样有记录，报告限用于实际送检样品。"),
    ("教育与培训", "changes", "培训取消、改期及退费均由乙方决定。", "培训改期、取消及已发生费用的退费结算规则由双方确认。"),
    ("法律与审计", "scope", "代理权限和审计范围均以乙方后续说明为准。", "委托事项、代理权限或审计范围及成果清单按具体服务附件执行。"),
    ("文化与知识产权", "license", "作品使用的期限、媒介和地域另议。", "许可期限、地域、媒介、使用次数及非独占范围已明确。"),
    ("其他服务", "scope", "服务范围与成果边界由服务方日后解释。", "服务范围、成果、排除事项及双方配合条件已在清单列明。"),
)


@pytest.mark.parametrize(("name", "check", "questionable", "adequate"), CASES)
async def test_each_type_has_real_instructions_and_does_not_invent_risks_for_sufficient_terms(
    monkeypatch, name, check, questionable, adequate,
):
    from app.agent.nodes import specialist
    from app.agent.review_profiles import matching_checks

    profile = PROFILES[name]
    selected = next(item for item in profile.checks if item.id == f"{profile.key}.{check}")
    assert selected in matching_checks(name, questionable)
    assert selected in matching_checks(name, adequate)
    assert matching_checks(name, "双方签字盖章，争议另按约定处理。") == ()
    with profile_scope(name):
        prompt = load_prompt("specialist_base", risk_dim=selected.risk_dim, stance="乙方", intensity="标准")
        assert selected.id in prompt
        for item in profile.checks:
            assert item.id in load_prompt(f"contract_profiles/{profile.key}")
        assert "不能仅" in load_prompt("review_scope", profile_name=name, checklist="[]") or "不从" in prompt or "不决定" in prompt

    async def adequate_reviewer(client, messages, tools, **kwargs):
        context = kwargs["context"]
        assert adequate in messages[1]["content"]
        assert selected.id in messages[1]["content"]
        return json.dumps({"risk_points": [], "check_results": [{
            "check_id": item["id"], "status": "reviewed",
            "reason": "已根据当前完整条款核对约定范围及附件引用；无需机械增加风险。",
            "clause_indices": [0],
        } for item in context["assigned_checks"]]}, ensure_ascii=False), []

    monkeypatch.setattr(specialist, "call_llm_with_tools", adequate_reviewer)
    output = await _run_specialist(asyncio.Semaphore(1), adequate, selected.risk_dim,
                                  {"contract_type": name, "stance": "乙方", "intensity": "标准", "chunks": [adequate]},
                                  object(), 0, True)
    assert output["result"] == []
    assert output["check_results"] and all(item["status"] == "reviewed" for item in output["check_results"])
    assert output["diagnostics"] == []


@pytest.mark.parametrize("record", [
    {}, {"status": "reviewed", "reason": "完成", "clause_indices": [1]},
    {"status": "reviewed", "reason": "完成", "clause_indices": [True]},
    {"status": "reviewed", "reason": "", "clause_indices": [0]},
    {"status": ["reviewed"], "reason": "完成", "clause_indices": [0]},
])
def test_missing_malformed_or_unread_clause_assessments_remain_unverified(record):
    check = PROFILES["信息化项目"].checks[0]
    record = {"check_id": check.id, **record}
    output = _check_results(json.dumps({"check_results": [record]}), [check],
                            {"clauses": ["当前全文", "只展示过目录"], "clause_reads": {0}})
    assert output[0]["status"] == "unverified"


def test_not_applicable_needs_full_contract_reads_and_duplicate_results_fail_closed():
    check = PROFILES["租赁服务"].checks[0]
    record = {"check_id": check.id, "status": "not_applicable", "reason": "没有该事项", "clause_indices": [0]}
    context = {"clauses": ["正文1", "正文2"], "clause_reads": {0}}
    assert _check_results(json.dumps({"check_results": [record]}), [check], context)[0]["status"] == "needs_material"
    context["clause_reads"].add(1)
    assert _check_results(json.dumps({"check_results": [record]}), [check], context)[0]["status"] == "not_applicable"
    assert _check_results(json.dumps({"check_results": [record, record]}), [check], context)[0]["status"] == "unverified"


def test_explicit_scope_exclusion_does_not_require_irrelevant_clauses():
    check = PROFILES["信息化项目"].checks[0]
    context = {"clauses": ["本项目仅提供既有软件在线许可，不涉及定制开发。", "争议解决。"], "clause_reads": {0}}
    record = {"check_id": check.id, "status": "not_applicable", "basis": "explicit_clause",
              "reason": "已读首条明示不涉及定制开发，不应机械要求交付定制源代码。", "clause_indices": [0]}
    assert _check_results(json.dumps({"check_results": [record]}), [check], context)[0]["status"] == "not_applicable"


async def test_empty_risks_without_specialty_records_is_incomplete(monkeypatch):
    from app.agent.nodes import arbitration, specialist

    async def empty(*args, **kwargs):
        return '{"risk_points":[]}', []

    async def summary(*args):
        return {"summary": "无风险", "suggestion": "", "overall_risk": "低"}

    monkeypatch.setattr(specialist, "call_llm_with_tools", empty)
    monkeypatch.setattr(arbitration, "_llm_summary", summary)
    state = {"contract_type": "信息化项目", "chunks": ["源代码按约交付"], "stance": "甲方", "intensity": "标准"}
    output = await _run_specialist(asyncio.Semaphore(1), state["chunks"][0], "验收交付与质保", state, object(), 0, True)
    assert output["diagnostics"] and output["check_results"][0]["status"] == "unverified"
    result = await arbitration.arbitration_node({**state, "gated": [], "specialist_outputs": [output], "errors": []})
    assert result["summary"]["review_status"] == "incomplete"
    assert result["summary"]["review_scope"]["checklist_status"] == "incomplete"


async def test_missing_specialty_record_gets_one_grounded_recovery_pass(monkeypatch):
    from app.agent.nodes import specialist

    check = PROFILES["信息化项目"].checks[0]

    async def missing_record(*args, **kwargs):
        kwargs["context"]["clause_reads"].add(1)
        return '{"risk_points":[]}', []

    class RecoveryClient:
        async def chat_structured(self, messages, **kwargs):
            payload = json.loads(messages[1]["content"])
            assert [item["index"] for item in payload["read_clauses"]] == [0, 1]
            return {"check_results": [{
                "check_id": check.id,
                "status": "reviewed",
                "reason": "已读取交付条款与附件条款，源代码及部署资料均有明确安排。",
                "clause_indices": [0, 1],
                "basis": "read_contract",
            }]}

    monkeypatch.setattr(specialist, "call_llm_with_tools", missing_record)
    monkeypatch.setattr(specialist, "get_sf_client", lambda: RecoveryClient())
    chunks = ["定制源代码应在验收时交付。", "部署文档及构建说明列入附件。"]
    output = await _run_specialist(
        asyncio.Semaphore(1), chunks[0], check.risk_dim,
        {"contract_type": "信息化项目", "stance": "甲方", "intensity": "标准", "chunks": chunks},
        object(), 0, True,
    )

    assert output["check_results"][0]["status"] == "reviewed"
    assert output["check_results"][0]["clause_indices"] == [0, 1]
    assert output["diagnostics"] == []


def test_scope_records_are_versioned_and_require_every_specialty_item():
    profile = PROFILES["信息化项目"]
    records = [{"check_id": check.id, "status": "reviewed", "reason": "已读正文支持", "clause_indices": [0]}
               for check in profile.checks]
    assert assessed_scope(profile.name, [{"check_results": records}])["checklist_status"] == "reviewed"
    assert assessed_scope(profile.name, [{"check_results": records[:-1]}])["checklist_status"] == "incomplete"
    assert assessed_scope(profile.name, [{"check_results": records}])["version"] == "1"
