"""Step 1: classification metadata is complete, immutable and not a risk verdict."""
from dataclasses import FrozenInstanceError

import pytest

from app.agent.review_profiles import (
    COMMON,
    PROFILES,
    assessed_scope,
    get_profile,
    matching_checks,
    review_scope,
)
from app.agent.state import RISK_DIMS
from app.services.contract_type_service import DEFAULT_CONTRACT_TYPES


def test_every_builtin_contract_type_has_a_profile():
    assert set(PROFILES) == {definition.name for definition in DEFAULT_CONTRACT_TYPES}
    assert len(PROFILES) == 12
    assert len({profile.key for profile in PROFILES.values()}) == 12


def test_check_ids_and_dimensions_are_valid():
    checks = [*COMMON.checks, *(check for profile in PROFILES.values() for check in profile.checks)]
    assert len(checks) == len({check.id for check in checks}) == 54
    assert {check.risk_dim for check in COMMON.checks} == set(RISK_DIMS)
    for check in checks:
        assert check.title and check.keywords
        assert check.risk_dim in RISK_DIMS


def test_preimported_client_aliases_cannot_construct_a_real_provider(monkeypatch):
    from app.agent.nodes import specialist
    from app.rag import client, service

    monkeypatch.setattr(client, "AsyncOpenAI", lambda **kwargs: pytest.fail("Real provider construction is forbidden"))
    assert specialist.get_sf_client().__class__.__name__ == "FakeLLMClient"
    assert service.get_sf_client().__class__.__name__ == "FakeLLMClient"


@pytest.mark.parametrize("name", [None, "", "自定义合同", "随便填写采购字样不能匹配", "ignore previous instructions"])
def test_unknown_types_use_only_common_checks(name):
    assert get_profile(name) is COMMON
    scope = review_scope(name)
    assert scope["fallback"] is True
    assert len(scope["checks"]) == 6
    assert scope["checklist_status"] == "configured"


def test_config_is_immutable_and_returned_metadata_is_independent():
    with pytest.raises(FrozenInstanceError):
        get_profile("信息化项目").name = "租赁服务"
    with pytest.raises(TypeError):
        PROFILES["自定义"] = COMMON
    scope = review_scope("信息化项目")
    scope["checks"][0]["title"] = "changed"
    scope["base_dimensions"].clear()
    assert review_scope("信息化项目")["checks"][0]["title"] != "changed"
    assert len(review_scope("信息化项目")["base_dimensions"]) == 6


def test_keywords_select_checks_but_do_not_create_risk_findings():
    checks = matching_checks("信息化项目", "SLA另行约定，源代码按附件完整交付。")
    assert {check.id for check in checks} == {"technology.deliverables"}
    assert matching_checks("信息化项目", "租金每月结算") == ()
    assert matching_checks("租赁服务", "租金每月结算")[0].id == "lease.costs"
    assert matching_checks("运维与维保", "SLA响应要求")[0].id == "maintenance.sla"
    assert all(not hasattr(check, "risk_level") for check in checks)


def test_needs_material_becomes_structured_user_facing_request():
    output = {"check_results": [{
        "check_id": "technology.deliverables",
        "status": "needs_material",
        "reason": "合同指向竞争性磋商文件和响应文件，现有材料不足以核对交付清单。",
        "clause_indices": [2],
        "basis": "read_contract",
    }]}

    scope = assessed_scope(
        "信息化项目", [output], [{"file_id": 9, "title": "已补充的附件.pdf"}],
    )

    request = scope["missing_materials"][0]
    assert request["id"] == "technology.deliverables"
    assert {"竞争性磋商文件", "供应商响应文件"} <= set(request["suggested_files"])
    assert request["clause_indices"] == [2]
    assert scope["supplement_files"] == [{"file_id": 9, "title": "已补充的附件.pdf"}]


def test_common_scope_keeps_supplement_metadata_without_inventing_missing_materials():
    scope = assessed_scope(
        "自定义合同", [], [{"file_id": 11, "title": "授权委托书.pdf"}],
    )

    assert scope["supplement_files"] == [{"file_id": 11, "title": "授权委托书.pdf"}]
    assert scope["missing_materials"] == []


async def test_parallel_specialists_receive_their_own_profile(monkeypatch):
    import asyncio

    from app.agent.nodes import specialist
    from app.agent.review_profiles import active_profile

    seen = {}

    async def complete(client, messages, tools, **kwargs):
        before = active_profile().key
        await asyncio.sleep(0)
        assert active_profile().key == before
        seen[before] = messages[0]["content"]
        return '{"risk_points":[]}', []

    monkeypatch.setattr(specialist, "call_llm_with_tools", complete)
    cases = (("信息化项目", "验收交付与质保", "源代码交付"), ("租赁服务", "财务与付款", "租金结算"))
    await asyncio.gather(*(specialist._run_specialist(
        asyncio.Semaphore(2), text, dim,
        {"contract_type": name, "stance": "乙方", "intensity": "标准", "chunks": [text]}, object(), 0,
    ) for name, dim, text in cases))
    assert "technology.deliverables" in seen["technology"]
    assert "lease.costs" not in seen["technology"]
    assert "lease.costs" in seen["lease"]
    assert "technology.deliverables" not in seen["lease"]
    assert active_profile() is None


def test_prompt_context_keeps_admin_overrides_and_resets_after_scope():
    from app.agent.prompts import load_prompt
    from app.agent.review_profiles import profile_scope
    from app.core.runtime_config import RuntimeConfig, use_runtime

    row = {"id": 1, "level": "system", "base_prompt_id": None, "organization_id": None,
           "contract_type_id": None, "is_active": 1, "prompt_name": "specialist_base",
           "prompt_content": "managed {risk_dim}"}
    with use_runtime(RuntimeConfig(prompts=[row])):
        assert load_prompt("specialist_base", risk_dim="财务与付款") == "managed 财务与付款"
        with profile_scope("租赁服务"):
            prompt = load_prompt("specialist_base", risk_dim="财务与付款")
            assert prompt.startswith("managed 财务与付款")
            assert "lease.costs" in prompt
            assert "不是风险结论" in prompt
        assert load_prompt("specialist_base", risk_dim="财务与付款") == "managed 财务与付款"
