"""已知重大例外不能被模型质检的误放行重新覆盖。"""
import pytest

from app.agent.rules.legal_guards import (
    guarded_legal_coverage_complete,
    legal_conclusion_errors,
    required_legal_findings,
)

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


def test_stale_retention_citation_is_replaced_by_verified_rules():
    clause = "逐项验收并出具验收书，电子档案留存15年；称实施条例第51条只管保存。"
    evidence = (
        "政府采购法·履约验收与采购文件 第四十二条至少保存十五年；"
        "政府采购法实施条例·履约验收 第四十六条可用电子档案保存；"
        "第五十一条应当及时支付采购资金。"
    )
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    assert all(token in findings[0]["risk_analysis"] for token in (
        "第四十二条", "第四十六条", "第五十一条", "及时支付",
    ))
    assert "符合履约验收要求" in findings[0]["risk_analysis"]


def test_government_service_scope_preserves_explicit_public_institution_fact():
    clause = "公益一类事业单位高校采购普通保洁服务，仅以服务期限3年认定违反政府购买服务办法。"
    evidence = (
        "政府购买服务管理办法：政府购买服务不等同所有政府采购服务；"
        "公益一类事业单位不能作为购买或承接主体。"
    )
    bad = {"risk_analysis": "【待确认】是否属于公益一类事业单位，不能排除该办法适用。",
           "suggested_content": "对照学校现行采购制度判断期限。"}
    errors = legal_conclusion_errors(bad, clause, evidence)
    assert len(errors) == 3
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    assert "第五条、第八条" in findings[0]["risk_analysis"]
    assert "不能仅因" in findings[0]["risk_analysis"]


def test_sensitive_information_finding_preserves_basis_and_checks_remaining_duties():
    clause = (
        "校园平台处理健康类敏感个人信息，已证明属于履行法定职责所必需，非基于同意；"
        "仍实施必要性审查、安全措施和影响评估。"
    )
    evidence = (
        "个人信息保护法·敏感信息与影响评估：敏感个人信息须有特定目的和充分必要性；"
        "处理前进行个人信息保护影响评估并留存记录。"
    )
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    text = findings[0]["risk_analysis"] + findings[0]["suggested_content"]
    assert all(token in text for token in ("非同意", "特定目的", "充分必要", "处理前", "留存"))
    assert guarded_legal_coverage_complete(clause, evidence, findings)


def test_technical_secret_default_right_stays_conditional():
    clause = "学校委托研发技术秘密成果，未另约转让权，乙方拟在向甲方交付前转让第三人。"
    evidence = (
        "民法典合同编·技术合同与知识产权：第八百六十一条规定交付前不得转让；"
        "依第五百一十条仍不能确定，且没有相同技术方案被授予专利权时适用默认规则。"
    )
    bad = {
        "risk_analysis": "双方都有使用和转让权，因此乙方可在交付后向第三人转让。",
        "suggested_content": "只限制交付前转让。",
    }
    assert legal_conclusion_errors(bad, clause, evidence)
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    assert guarded_legal_coverage_complete(clause, evidence, findings)
    assert legal_conclusion_errors(findings[0], clause, evidence) == []


def test_delivered_secret_with_confirmed_default_conditions_does_not_get_pre_delivery_finding():
    clause = (
        "委托开发的技术秘密成果已向学校交付，双方无约定且补充解释仍不能确定权利，"
        "同一技术方案尚未获专利。学校主张只有学校能够使用或转让。"
    )
    evidence = (
        "民法典合同编·技术合同与知识产权：第八百六十一条；依第五百一十条仍不能确定，"
        "没有相同技术方案被授予专利权时双方均有使用和转让权。"
    )
    assert required_legal_findings(clause, evidence, []) == []


def test_emergency_exception_does_not_unconditionally_reintroduce_notice_duties():
    clause = (
        "合同名称写紧急采购，无需核验严重自然灾害或其他不可抗力，"
        "一律不适用政府采购法。"
    )
    evidence = "政府采购法·总则与适用范围：第八十五条规定严重自然灾害和其他不可抗力例外。"
    bad = {
        "risk_analysis": "应核验实际采购目的。",
        "suggested_content": "同时明确7个工作日备案、2个工作日公告。",
    }
    good = {
        **bad,
        "suggested_content": "若第八十五条例外不成立，合同仍受政府采购法调整时再备案、公告。",
    }
    assert legal_conclusion_errors(bad, clause, evidence)
    assert legal_conclusion_errors(good, clause, evidence) == []
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    assert "实际采购目的" in findings[0]["risk_analysis"]


def test_data_retention_coverage_distinguishes_records_and_commercial_use():
    clause = "因处理记录至少保存3年，退出后保留全部业务数据用于训练商业模型。"
    evidence = "处理记录至少保存3年；法定保存例外不允许继续处理。"
    points = [{
        "risk_analysis": "处理记录不等于全部业务数据，保存例外不允许训练。",
        "suggested_content": "业务数据退出时删除，不得用于商业训练。",
    }]
    assert guarded_legal_coverage_complete(clause, evidence, points)


def test_unverified_supplier_size_keeps_payment_rule_conditional():
    clause = "2026年签约，甲方为事业单位高校，乙方企业规模尚未核实。设备验收后90日付款。"
    evidence = (
        "保障中小企业款项支付条例·付款期限与验收（2025修订）：先核对供方订约时是否"
        "属于中小企业；事业单位另有约定最长不得超过60日。"
    )
    bad = {"risk_analysis": "甲方为事业单位，本合同适用保障中小企业款项支付条例，"
                            "90日超过法定上限。", "suggested_content": "改为60日。"}
    assert legal_conclusion_errors(bad, clause, evidence)
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    assert guarded_legal_coverage_complete(clause, evidence, findings)


def test_large_enterprise_payment_finding_preserves_third_party_condition():
    clause = (
        "2026年签约，甲方为大型企业，乙方为中小企业。付款期限约定90日，是否符合行业规范"
        "和交易习惯尚待核验，不以收到第三方款项为付款条件。"
    )
    evidence = (
        "保障中小企业款项支付条例·付款期限与验收（2025修订）：大型企业向中小企业采购"
        "原则上60日；另约时按行业规范和交易习惯合理约定；不得约定收到第三方款项才付款。"
    )
    incomplete = [{
        "risk_analysis": "大型企业90日账期须核验行业规范和交易习惯，不当然违法。",
        "suggested_content": "留存账期依据。",
    }]
    findings = required_legal_findings(clause, evidence, incomplete)
    assert len(findings) == 1
    text = findings[0]["risk_analysis"] + findings[0]["suggested_content"]
    assert "第三方款项" in text and "符合" in text
    assert guarded_legal_coverage_complete(clause, evidence, incomplete + findings)


def test_existing_software_ownership_still_checks_component_licence():
    clause = (
        "学校委托开发软件，书面合同明确约定可转让的软件著作财产权归学校，"
        "署名权依法保留，既有组件另附许可清单。"
    )
    evidence = (
        "计算机软件保护条例·委托开发与许可边界：已明确约定归委托人的，应先按该约定核对；"
        "核验既有组件、定制模块及使用修改维护许可和第三方权利。"
    )
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    assert guarded_legal_coverage_complete(clause, evidence, findings)


def test_unquantified_loss_does_not_create_waiver_or_fixed_reduction():
    clause = (
        "合同违约金为合同总价40%。双方称合同金额30%是上限并自动无效。"
        "实际损失尚未核定。"
    )
    evidence = (
        "合同编通则司法解释·违约金调整；民法典第585条：以造成的损失为基础，"
        "高出损失30%是参照，须提出请求并举证。"
    )
    bad = {"risk_analysis": "继续履行可能自认放弃违约金请求权。", "suggested_content": "保留40%。"}
    assert legal_conclusion_errors(bad, clause, evidence)
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    assert guarded_legal_coverage_complete(clause, evidence, findings)


def test_malicious_breach_reduction_covers_all_conditions_without_assuming_fact():
    clause = (
        "违约方被指恶意违约，是否属实仍需举证。合同约定禁止法院调整违约金，"
        "违约方要求不问实际损失及履行情况一律减半。"
    )
    evidence = (
        "合同编通则司法解释·违约金调整：不能排除司法调整；结合实际损失、履行、过错和举证；"
        "恶意违约请求调减通常不获支持。"
    )
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    assert guarded_legal_coverage_complete(clause, evidence, findings)


def test_foreign_china_court_choice_does_not_invent_specific_court_requirement():
    clause = (
        "经核实属于涉外民事纠纷，双方书面协议选择中国人民法院管辖，尚需核查级别与专属限制；"
        "一方主张仅因争议与我国无实际联系，该选择当然无效。"
    )
    evidence = (
        "民事诉讼法·协议管辖与实际联系（2023修正）：第277条不要求争议与我国必须有实际联系；"
        "仍核验级别及专属管辖。"
    )
    bad = {"risk_analysis": "未指明具体法院，约定不明。", "suggested_content": "明确约定具体法院。"}
    assert legal_conclusion_errors(bad, clause, evidence)
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    assert guarded_legal_coverage_complete(clause, evidence, findings)


def test_domestic_arbitration_keeps_finality_and_checks_named_institution():
    clause = (
        "2026年签订的普通国内采购合同，双方书面约定争议提交深圳国际仲裁院仲裁，"
        "仲裁裁决一裁终局。"
    )
    evidence = (
        "仲裁法·仲裁协议与一裁终局（2025修订）：一裁终局；书面协议须有仲裁意思和"
        "可确定机构；第82条只适用于特定涉外情形。"
    )
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    assert guarded_legal_coverage_complete(clause, evidence, findings)
    text = findings[0]["risk_analysis"] + findings[0]["suggested_content"]
    assert "一裁终局" in text and "本身不是" in text and "普通国内" in text


def test_complete_force_majeure_clause_is_not_rewritten_as_missing_details():
    clause = (
        "因不可抗力实际影响履行的，双方按影响范围处理，及时通知并在合理期限提供证明，"
        "合理减损；不免除迟延履行后发生不可抗力时的既有违约责任。"
    )
    evidence = "第五百九十条规定通知、证明及迟延例外；第五百九十一条规定合理减损。"
    bad = {
        "risk_analysis": "条款仅约定“及时通知”，未明确通知方式和具体天数，约束力偏弱。",
        "suggested_content": "固定三日通知。",
    }
    assert legal_conclusion_errors(bad, clause, evidence)
    findings = required_legal_findings(clause, evidence, [])
    assert len(findings) == 1
    assert guarded_legal_coverage_complete(clause, evidence, findings)


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
    assert result["errors"] == [] and len(streamed) == 1
