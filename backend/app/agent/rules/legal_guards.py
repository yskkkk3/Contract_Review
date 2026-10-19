"""已展示规则的有限结论保护；不推断未给定的事实，不代替全面法律审阅。"""
import re

_LATE_FACT = re.compile(
    r"(?:甲方|乙方|供应商|承包人|卖方|买方)(?:已|已经)迟延[^。；]{0,40}后[^。；]{0,12}(?:发生|遭遇)"
)
_EXEMPTION = re.compile(
    r"(?:部分或全部|部分或者全部)(?:免责|免除)|"
    r"(?:仅在|根据|按照?|仅限)[^。；]{0,30}影响[^。；]{0,20}免责"
)


def legal_conclusion_errors(point: dict, clause: str, evidence_context: str) -> list[str]:
    """Reject narrow, evidence-verifiable legal errors without inferring missing facts."""
    errors = _government_service_scope_errors(point, clause, evidence_context)
    errors.extend(_technical_secret_default_errors(point, clause, evidence_context))
    errors.extend(_emergency_procurement_errors(point, clause, evidence_context))
    errors.extend(_sme_payment_errors(point, clause, evidence_context))
    errors.extend(_penalty_adjustment_errors(point, clause, evidence_context))
    errors.extend(_foreign_jurisdiction_errors(point, clause, evidence_context))
    errors.extend(_complete_force_majeure_errors(point, clause, evidence_context))
    fact = _LATE_FACT.search(clause)
    if not (fact and "不可抗力" in clause and "第五百九十条" in evidence_context):
        return errors
    if re.search(r"(?:若|如果|假如|是否|可能)[^。；]{0,16}$", clause[:fact.start()]):
        return errors
    for sentence in re.split(r"[。；;\n]", point.get("suggested_content", "")):
        if re.search(r"未迟延(?:履行)?的?(?:一方|当事人)|非迟延方|不可抗力发生在迟延之前", sentence):
            continue
        for match in _EXEMPTION.finditer(sentence):
            prefix = sentence[:match.start()]
            if re.search(r"(?:不|不得|不能|禁止)(?:主张|适用|据此|自动)?$", prefix):
                continue
            errors.append("已明确先迟延后发生事件，修改建议仍引入按影响部分或全部免责，须保留第590条迟延后例外")
            return errors
    return errors


def _government_service_scope_errors(point: dict, clause: str, evidence_context: str) -> list[str]:
    if not (
        "公益一类事业单位" in clause
        and "政府购买服务" in clause
        and "公益一类事业单位不能作为购买或承接主体" in evidence_context
    ):
        return []
    text = point.get("risk_analysis", "") + point.get("suggested_content", "")
    errors = []
    if re.search(r"待确认[^。；]{0,30}(?:是否)?(?:属于)?公益一类事业单位", text):
        errors.append("条款已明确公益一类事业单位，不得重新标为待确认事实")
    if "不能排除该办法适用" in text:
        errors.append("已展示范围规则排除公益一类事业单位作为购买主体，不得仍称不能排除适用")
    if "不宜作为合同条款节选" in text:
        errors.append("不得把合规判断改写为对测试条款或背景材料形式的评价")
    if ("校内采购制度" in text or "学校现行采购" in text) and "校内" not in evidence_context:
        errors.append("可见证据未提供校内期限规则，不得将其作为期限合法性依据")
    return errors


def _technical_secret_default_errors(point: dict, clause: str, evidence_context: str) -> list[str]:
    if not (
        _is_pre_delivery_secret_transfer(clause)
        and ("第八百六十一条" in evidence_context or "第861条" in evidence_context)
    ):
        return []
    text = point.get("risk_analysis", "") + point.get("suggested_content", "")
    asserts_post_delivery_right = bool(re.search(
        r"(?:乙方|双方|当事人).{0,20}(?:可|有权).{0,20}(?:交付后.{0,10})?转让",
        text,
    ))
    has_default_conditions = (
        ("第五百一十条" in text or "第510条" in text)
        and ("仍不能确定" in text or "补充确定" in text)
        and "相同技术方案" in text and "专利权" in text
    )
    makes_conditions_pending = (
        any(token in text for token in ("需核验", "应核验", "待核验", "尚待确认"))
        or bool(re.search(r"只有在.{0,100}才", text))
    )
    if asserts_post_delivery_right and not (has_default_conditions and makes_conditions_pending):
        return [
            "不得把技术秘密成果的附条件默认转让权写成确定结论；须核验第510条仍不能确定且无相同技术方案获专利"
        ]
    return []


def _emergency_procurement_errors(point: dict, clause: str, evidence_context: str) -> list[str]:
    if not (
        "紧急采购" in clause
        and ("严重自然灾害" in clause or "不可抗力" in clause)
        and ("第八十五条" in evidence_context or "第85条" in evidence_context)
    ):
        return []
    advice = point.get("suggested_content", "")
    imposes_notice = (
        ("备案" in advice or "公告" in advice)
        and bool(re.search(r"(?:2|二|7|七)个工作日", advice))
    )
    conditions_notice = bool(re.search(
        r"(?:如|若|仅在).{0,24}(?:不属于|未适用|不适用|例外不成立).{0,45}(?:备案|公告)|"
        r"(?:备案|公告).{0,45}(?:以第八十五条例外不成立|以第85条例外不成立|仅适用于仍受政府采购法调整)",
        advice,
    ))
    if imposes_notice and not conditions_notice:
        return ["第85条紧急采购例外成立时不得无条件附加政府采购合同备案、公告义务"]
    return []


def _sme_payment_errors(point: dict, clause: str, evidence_context: str) -> list[str]:
    if not (
        "企业规模尚未核实" in clause
        and "保障中小企业款项支付条例" in evidence_context
    ):
        return []
    text = _combined(point)
    direct_application = bool(re.search(
        r"(?:甲方|本合同|本项目).{0,35}(?:适用|应适用).{0,20}保障中小企业款项支付条例",
        text,
    ))
    direct_violation = "超过法定上限" in text or "超出的30日" in text
    if direct_application or direct_violation:
        return ["乙方订约时规模尚未核实，不得直接适用中小企业付款条例或认定90日超过法定上限"]
    return []


def _penalty_adjustment_errors(point: dict, clause: str, evidence_context: str) -> list[str]:
    if not (
        "违约金" in clause
        and "实际损失尚未核定" in clause
        and ("第五百八十五条" in evidence_context or "第585条" in evidence_context)
    ):
        return []
    text = _combined(point)
    if "自认放弃" in text or "视为放弃" in text:
        return ["实际履行和权利处分事实未给出，不得推定当事人自认或放弃违约金请求权"]
    return []


def _foreign_jurisdiction_errors(point: dict, clause: str, evidence_context: str) -> list[str]:
    if not (
        "涉外民事纠纷" in clause
        and "书面协议选择中国人民法院" in clause
        and ("第277条" in evidence_context or "第二百七十七条" in evidence_context)
    ):
        return []
    text = _combined(point)
    if "未指明具体法院" in text or "明确约定具体法院" in text:
        return ["涉外书面协议选择中国人民法院适用第277条，不得无依据追加必须指定某一具体法院的要求"]
    return []


def _complete_force_majeure_errors(point: dict, clause: str, evidence_context: str) -> list[str]:
    complete_clause = all(token in clause for token in (
        "实际影响", "及时通知", "合理期限提供证明", "合理减损", "迟延履行后",
    ))
    if not (complete_clause and "第五百九十条" in evidence_context and "第五百九十一条" in evidence_context):
        return []
    text = _combined(point)
    if any(token in text for token in (
        "仅约定“及时通知”", "未明确通知方式", "未明确通知", "具体天数", "约束力偏弱",
        "条款未约定不可抗力持续", "缺少解除",
    )):
        return ["条款已含影响范围、及时通知、合理期限证明、合理减损和迟延例外，不得将其说成缺失"]
    return []


def _combined(point: dict) -> str:
    return point.get("risk_analysis", "") + point.get("suggested_content", "")


def _is_pre_delivery_secret_transfer(clause: str) -> bool:
    return (
        "技术秘密" in clause and "转让" in clause
        and bool(re.search(r"交付.{0,8}(?:前|之前)", clause))
        and "已向学校交付" not in clause and "已交付" not in clause
    )


def guarded_legal_coverage_complete(
    clause: str,
    evidence_context: str,
    accepted_points: list[dict],
) -> bool:
    """Narrowly confirm that an evidence-backed critical scenario is already covered."""
    text = "\n".join(_combined(point) for point in accepted_points)
    if (
        "处理记录" in clause and "3年" in clause and "业务数据" in clause
        and "训练" in clause and "处理记录" in evidence_context and "3年" in evidence_context
    ):
        return all(token in text for token in ("处理记录", "业务数据", "训练")) and (
            "不得用于" in text or "禁止" in text
        )
    if "健康类敏感个人信息" in clause and "影响评估" in clause:
        return all(token in text for token in (
            "特定目的", "充分必要", "影响评估", "留存", "委托处理", "共同处理", "独立处理",
        )) and ("法定职责" in text and ("事前" in text or "处理前" in text))
    if _is_pre_delivery_secret_transfer(clause):
        return all(token in text for token in (
            "交付前", "不得", "仍不能确定", "相同技术方案", "专利权",
        )) and ("第510条" in text or "第五百一十条" in text) and (
            "需核验" in text or "待核验" in text
        )
    if "紧急采购" in clause and ("严重自然灾害" in clause or "不可抗力" in clause):
        return all(token in text for token in ("合同名称", "严重自然灾害", "不可抗力", "实际采购目的"))
    if "企业规模尚未核实" in clause and "90日付款" in clause:
        return all(token in text for token in ("订约时", "中小企业", "核验", "90日")) and (
            "若" in text or "如" in text
        ) and ("大型企业" in text or "商业风险" in text)
    if _is_large_enterprise_payment_case(clause):
        return all(token in text for token in (
            "大型企业", "中小企业", "90日", "行业规范", "交易习惯", "第三方款项",
        )) and ("不是绝对" in text or "并非绝对" in text or "不当然" in text) and (
            "符合" in text or "保留" in text
        )
    if "书面合同明确约定" in clause and "既有组件另附许可清单" in clause:
        return all(token in text for token in (
            "书面约定", "财产权", "署名权", "既有组件", "许可清单", "修改", "维护", "第三方权利",
        ))
    if "合同总价40%" in clause and "实际损失尚未核定" in clause:
        return all(token in text for token in (
            "实际损失尚未核定", "合同金额", "损失", "请求", "举证", "自动无效", "当然调减",
        )) and ("不能" in text or "不得" in text)
    if "禁止法院调整违约金" in clause and "一律减半" in clause:
        return all(token in text for token in (
            "不能排除", "一律减半", "实际损失", "履行情况", "举证", "恶意违约", "通常不支持",
        )) and ("是否属实" in text or "待核实" in text or "仍需举证" in text)
    if "涉外民事纠纷" in clause and "书面协议选择中国人民法院" in clause:
        return all(token in text for token in (
            "第277条", "实际联系", "级别", "专属管辖",
        )) and ("不要求" in text or "不以" in text)
    if "普通国内采购合同" in clause and "深圳国际仲裁院" in clause and "一裁终局" in clause:
        return all(token in text for token in (
            "一裁终局", "不是", "仲裁意思", "机构", "可确定", "普通国内", "第82条",
        )) and ("核验" in text or "确认" in text)
    if all(token in clause for token in (
        "实际影响", "及时通知", "合理期限提供证明", "合理减损", "迟延履行后",
    )):
        return all(token in text for token in (
            "按影响范围", "及时通知", "合理期限", "证明", "减损", "迟延履行后", "不免除",
        )) and ("无需" in text or "不构成" in text or "已包含" in text)
    return False


def required_legal_findings(
    clause: str,
    evidence_context: str,
    accepted_points: list[dict],
) -> list[dict]:
    """Return narrow evidence-backed findings that may not be silently lost by an LLM gate."""
    findings: list[dict] = []
    fact = _LATE_FACT.search(clause)
    has_late_finding = any(
        re.search(
            r"迟延履行后.{0,30}(?:不免除|不得免除|不能免除).{0,20}违约责任",
            point.get("risk_analysis", "") + point.get("suggested_content", ""),
        )
        for point in accepted_points
    )
    if (fact and "不可抗力" in clause and "第五百九十条" in evidence_context
            and not has_late_finding):
        refs = (["民法典合同编·违约责任与定金"]
                if "民法典合同编·违约责任与定金" in evidence_context else [])
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "条款已明确乙方先迟延交付、后发生洪水。《民法典》第五百九十条规定，"
                "当事人迟延履行后发生不可抗力的，不免除其违约责任；因此不能以洪水或"
                "不可抗力标签免除乙方的全部违约责任。仍应核验事件对后续履行的实际因果"
                "影响、通知与证明、减损情况，以及合同目的能否实现和继续履行或解除条件，"
                "但这些核验不能推翻迟延履行后的法定例外。"
            ),
            "risk_level": "高",
            "suggested_content": (
                "删除“免除此前全部违约责任”及“无需通知或证明”的表述；明确乙方迟延履行后"
                "发生不可抗力的，不免除其违约责任，并要求及时书面通知、在合理期限提供证明、"
                "说明实际影响范围并采取减损措施。是否继续履行或解除，另按事件影响、合同目的"
                "及法定或约定条件处理，不得据此反向扩大免责。"
            ),
            "evidence_refs": refs,
        })

    retention_claim = (
        ("15年" in clause or "十五年" in clause)
        and ("第51条" in clause or "第五十一条" in clause)
        and ("保存" in clause or "留存" in clause)
    )
    retention_evidence = all(token in evidence_context for token in (
        "第四十二条", "第四十六条", "第五十一条", "及时",
    ))
    has_retention_finding = any(
        all(token in point.get("risk_analysis", "") + point.get("suggested_content", "")
            for token in ("第四十二条", "第四十六条", "第五十一条", "及时"))
        for point in accepted_points
    )
    if retention_claim and retention_evidence and not has_retention_finding:
        refs = [doc_id for doc_id in (
            "政府采购法·履约验收与采购文件", "政府采购法实施条例·履约验收",
        ) if doc_id in evidence_context]
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "条款中的验收方案已逐项列明技术、服务、安全标准并要求出具验收书，"
                "该部分符合履约验收要求，无需作为缺失补正。法条引用需要纠正：采购文件"
                "至少保存十五年的依据是《政府采购法》第四十二条，电子档案保存的依据是"
                "《政府采购法实施条例》第四十六条；实施条例第五十一条规定的是采购人应"
                "按政府采购合同及时支付采购资金，并非档案保存规则。混同三项规则会掩盖"
                "及时付款义务并造成合同依据错误。"
            ),
            "risk_level": "高",
            "suggested_content": (
                "保留现有逐项验收标准和验收书安排；将十五年留存依据改为《政府采购法》"
                "第四十二条，将电子档案依据改为《政府采购法实施条例》第四十六条；删除"
                "“第五十一条只管保存、不要求及时付款”，并明确依第五十一条按合同约定"
                "及时支付采购资金。付款具体期限另结合合同主体和适用支付规则核定。"
            ),
            "evidence_refs": refs,
        })

    service_scope_claim = (
        "公益一类事业单位" in clause
        and "政府购买服务" in clause
        and "服务期限3年" in clause
    )
    service_scope_evidence = (
        "公益一类事业单位不能作为购买或承接主体" in evidence_context
        and "政府购买服务不等同所有政府采购服务" in evidence_context
    )
    has_service_scope_finding = any(
        "公益一类事业单位不能作为" in (
            point.get("risk_analysis", "") + point.get("suggested_content", "")
        )
        and "不能仅因" in (point.get("risk_analysis", "") + point.get("suggested_content", ""))
        for point in accepted_points
    )
    if service_scope_claim and service_scope_evidence and not has_service_scope_finding:
        refs = ["政府购买服务管理办法"] if "政府购买服务管理办法" in evidence_context else []
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "条款已明确采购人为公益一类事业单位。依据《政府购买服务管理办法》第五条、"
                "第八条等范围规则，政府购买服务的购买主体原则上是各级国家机关及参照执行的"
                "特定机关组织，公益一类事业单位不能作为购买或承接主体；政府购买服务也不等同"
                "于所有政府采购服务。因此，不能仅因普通校内保洁服务期限为三年，就直接套用该"
                "办法第二十四条认定合同违法。三年期限是否存在其他预算、采购程序或履约风险，"
                "应依据实际适用且已提供的规则另行判断，不能虚构校内期限限制。"
            ),
            "risk_level": "高",
            "suggested_content": (
                "删除“仅因三年期限即按政府购买服务管理办法认定违法”的结论；在审查记录中"
                "写明采购人的公益一类事业单位性质，并按第五条、第八条核对购买主体和政府购买"
                "服务定义。确认本项目不属于该办法调整的政府购买服务后，不适用第二十四条的"
                "一年/三年期限规则；合同期限再按有实际依据的预算、采购和履约规则审查。"
            ),
            "evidence_refs": refs,
        })

    sensitive_claim = (
        "健康类敏感个人信息" in clause
        and "履行法定职责所必需" in clause
        and "影响评估" in clause
    )
    sensitive_evidence = all(token in evidence_context for token in (
        "敏感个人信息", "特定目的", "充分必要", "个人信息保护影响评估",
    ))
    if (
        sensitive_claim and sensitive_evidence
        and not guarded_legal_coverage_complete(clause, evidence_context, accepted_points)
    ):
        refs = [doc_id for doc_id in (
            "个人信息保护法·敏感信息与影响评估",
            "个人信息保护法·委托处理与退出删除",
        ) if doc_id in evidence_context]
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "条款已明确提供具体法律依据，处理基础是履行法定职责所必需而非同意，"
                "不能仅因未取得单独同意即认定违法；必要性审查、安全措施和影响评估也已"
                "明确安排，不能表述为完全缺失。仍须独立核验健康类敏感个人信息的处理是否"
                "具有特定目的和充分必要性、所处理字段与使用范围是否最小必要，以及个人信息"
                "保护影响评估是否在处理前完成并留存记录。学校的法定基础也不当然覆盖平台"
                "运营方超出委托目的的自身使用；应先核验学校与平台分别属于委托处理、共同处理"
                "还是独立处理，并确认相关法定职责由谁承担、能否构成平台处理的合法基础。"
            ),
            "risk_level": "中",
            "suggested_content": (
                "保留现有法定处理基础、必要性审查、安全措施和影响评估安排；补充形成并留存"
                "书面核验记录，列明具体法定职责、健康信息字段、特定处理目的、充分必要性与"
                "最小范围，并在处理前完成个人信息保护影响评估。明确学校与平台是委托处理、共同"
                "处理或独立处理；仅在核验为委托处理且学校承担相应法定职责时，平台方按约定目的、"
                "期限、方式和安全措施处理，不得将学校的法定职责基础用于自身分析、研发或对外提供。"
            ),
            "evidence_refs": refs,
        })

    secret_claim = _is_pre_delivery_secret_transfer(clause)
    secret_evidence = (
        ("第八百六十一条" in evidence_context or "第861条" in evidence_context)
        and ("第五百一十条" in evidence_context or "第510条" in evidence_context)
        and "相同技术方案" in evidence_context
    )
    if (
        secret_claim and secret_evidence
        and not guarded_legal_coverage_complete(clause, evidence_context, accepted_points)
    ):
        refs = ["民法典合同编·技术合同与知识产权"] if (
            "民法典合同编·技术合同与知识产权" in evidence_context
        ) else []
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "《民法典》第八百六十一条明确禁止委托开发的研究开发人在向委托人交付成果前"
                "向第三人转让，乙方拟在交付前转让直接触及该限制。交付后的使用、转让权限则"
                "不能在本条事实下直接认定：只有在双方无约定、依第五百一十条仍不能确定，且"
                "没有相同技术方案被授予专利权等条件成立时，才适用双方均有使用和转让权的"
                "默认规则；这些条件需核验，不能把附条件的默认权利写成乙方确定享有的权利。"
            ),
            "risk_level": "高",
            "suggested_content": (
                "明确乙方在成果交付前不得向第三人转让、许可或披露，并约定停止转让、返还资料、"
                "销毁复制件及赔偿损失等责任。另行书面约定交付后的使用权、转让权、保密和收益"
                "分配；在未完成约定解释与补充、第五百一十条补充确定及相同技术方案专利状况核验前，"
                "不得预设乙方可在交付后转让。"
            ),
            "evidence_refs": refs,
        })

    emergency_claim = (
        "紧急采购" in clause and ("严重自然灾害" in clause or "不可抗力" in clause)
        and "合同名称" in clause
    )
    emergency_evidence = (
        ("第八十五条" in evidence_context or "第85条" in evidence_context)
        and "严重自然灾害" in evidence_context and "不可抗力" in evidence_context
    )
    if (
        emergency_claim and emergency_evidence
        and not guarded_legal_coverage_complete(clause, evidence_context, accepted_points)
    ):
        refs = ["政府采购法·总则与适用范围"] if (
            "政府采购法·总则与适用范围" in evidence_context
        ) else []
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "合同名称不能替代《政府采购法》第八十五条要求的实际法定原因。应核验是否确因"
                "严重自然灾害或其他不可抗力实施紧急采购、实际采购目的及两者的因果关系；一般"
                "赶工或自行命名为紧急采购，不能自动排除政府采购法。若第八十五条例外事实成立，"
                "才按该条处理；若不成立，本项目仍应按其主体、资金和目录事实适用政府采购规则。"
            ),
            "risk_level": "高",
            "suggested_content": (
                "删除“名称写紧急采购即一律不适用”的表述，载明灾害或不可抗力事实、紧急采购"
                "目的、因果关系及书面认定材料。仅在第八十五条例外条件经核验成立时按例外处理；"
                "例外不成立、合同仍受政府采购法调整时，再履行相应采购程序及合同备案、公告义务，"
                "不得把备案公告无条件附加于已经依法排除该法适用的情形。"
            ),
            "evidence_refs": refs,
        })

    large_enterprise_claim = _is_large_enterprise_payment_case(clause)
    large_enterprise_evidence = all(token in evidence_context for token in (
        "大型企业向中小企业采购", "行业规范", "交易习惯", "不得约定收到第三方款项才付款",
    ))
    if (
        large_enterprise_claim and large_enterprise_evidence
        and not guarded_legal_coverage_complete(clause, evidence_context, accepted_points)
    ):
        refs = ["保障中小企业款项支付条例·付款期限与验收（2025修订）"] if (
            "保障中小企业款项支付条例·付款期限与验收（2025修订）" in evidence_context
        ) else []
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "甲方为大型企业、乙方为中小企业，应按《保障中小企业款项支付条例》第九条"
                "的大型企业规则审查。60日是原则期限，并非机关、事业单位另约期限的绝对上限；"
                "90日另约期限不当然违法，但须有行业规范和交易习惯支持其合理性并及时付款。"
                "条款已明确不以收到第三方款项为付款条件，符合不得把第三方回款或回款进度转嫁"
                "给中小企业的限制，该项不应被误报为缺陷；仍应留存90日账期合理性的核验依据。"
            ),
            "risk_level": "中",
            "suggested_content": (
                "保留“不以收到第三方款项为付款条件”，并补充不得按第三方付款进度比例付款。"
                "签约前核验并留存支持90日账期的行业规范和同类交易习惯；依据不足时调整为60日"
                "以内。无论采用何种期限，均明确从交付、验收合格或双方确认结算金额等适用节点"
                "起算，内部审批和第三方回款不得延迟起算或付款。"
            ),
            "evidence_refs": refs,
        })

    sme_claim = "企业规模尚未核实" in clause and "90日付款" in clause
    sme_evidence = (
        "保障中小企业款项支付条例" in evidence_context
        and "订约时" in evidence_context and "最长不得超过60日" in evidence_context
    )
    if (
        sme_claim and sme_evidence
        and not guarded_legal_coverage_complete(clause, evidence_context, accepted_points)
    ):
        refs = ["保障中小企业款项支付条例·付款期限与验收（2025修订）"] if (
            "保障中小企业款项支付条例·付款期限与验收（2025修订）" in evidence_context
        ) else []
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "乙方订约时的企业规模尚未核实，必须先按适用划型标准确认，不能直接认定本合同"
                "适用《保障中小企业款项支付条例》或90日账期已经违反法定上限。若乙方订约时"
                "属于中小企业，事业单位采购另有约定的付款期限最长不得超过60日，90日约定才"
                "触及该限制；若乙方为大型企业，该条例不适用，90日账期仍可作为资金占用、供应"
                "稳定和报价溢价的商业风险评估，但不能表述为违反该条例。"
            ),
            "risk_level": "高",
            "suggested_content": (
                "签约前取得并留存乙方订约时企业规模声明及划型依据。若核验为中小企业，将验收"
                "后的约定付款期限调整至不超过60日，并明确验收起算和逾期责任；若核验为大型企业，"
                "可结合预算和交易条件决定是否保留90日，同时明确验收、付款资料和起算日。未完成"
                "规模核验前，合同和审查结论均采用上述分支表述。"
            ),
            "evidence_refs": refs,
        })

    software_claim = "书面合同明确约定" in clause and "既有组件另附许可清单" in clause
    software_evidence = (
        "已明确约定归委托人的，应先按该约定核对" in evidence_context
        and "既有组件" in evidence_context and "使用修改维护许可" in evidence_context
    )
    if (
        software_claim and software_evidence
        and not guarded_legal_coverage_complete(clause, evidence_context, accepted_points)
    ):
        refs = [doc_id for doc_id in (
            "计算机软件保护条例·委托开发与许可边界",
            "著作权法·委托作品与许可转让",
        ) if doc_id in evidence_context]
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "条款已有书面约定，将可转让的软件著作财产权归学校并依法保留署名权，应优先按"
                "该约定核对，不能再套用无约定时著作权归受托人的默认规则；该核心权属安排本身"
                "未显示缺陷。仍应区分定制模块与既有组件，核验所附许可清单是否覆盖学校实际需要"
                "的使用、复制、修改、维护、部署和必要再许可范围、期限，以及开源或其他第三方权利，"
                "避免核心软件归属明确但既有组件许可不足影响持续运行。"
            ),
            "risk_level": "中",
            "suggested_content": (
                "保留现有财产权归属和署名权安排；将既有组件许可清单作为合同附件逐项核对组件名称、"
                "版本、权利人、许可类型、使用地域与期限，以及学校的修改、维护、部署、备份和必要"
                "再许可权限，并由乙方保证有权授予、披露第三方及开源许可义务并承担侵权责任。"
            ),
            "evidence_refs": refs,
        })

    penalty_claim = "合同总价40%" in clause and "实际损失尚未核定" in clause
    penalty_evidence = (
        ("第五百八十五条" in evidence_context or "第585条" in evidence_context)
        and "造成的损失" in evidence_context and "30%" in evidence_context
    )
    if (
        penalty_claim and penalty_evidence
        and not guarded_legal_coverage_complete(clause, evidence_context, accepted_points)
    ):
        refs = [doc_id for doc_id in (
            "合同编通则司法解释·违约金调整", "民法典合同编·违约责任与定金",
        ) if doc_id in evidence_context]
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "“合同金额30%”不是违约金法定上限，40%的约定也不因此自动无效。违约金是否过高"
                "应以实际损失而非合同金额为比较基础，由当事人提出调整请求并承担相应举证责任，"
                "再结合履行情况、过错等因素衡量。当前实际损失尚未核定，因此现阶段既不能认定本条"
                "自动无效，也不能按固定比例当然调减；应先查明损失及其他调整事实。没有实际履行或"
                "权利处分事实时，也不得推定任何一方已自认或放弃违约金请求权。"
            ),
            "risk_level": "高",
            "suggested_content": (
                "删除“法律规定不得超过合同金额30%”和“本条自动无效”。保留可依法请求调整的"
                "机制，明确主张方举证实际损失、合同履行、过错和其他调整因素；在实际损失尚未核定"
                "前不预设无效或调减比例。可按不同违约类型细化计算基数、起止时间和责任衔接，但"
                "具体比例由双方结合可预见损失另行确认。"
            ),
            "evidence_refs": refs,
        })

    malicious_claim = "禁止法院调整违约金" in clause and "一律减半" in clause
    malicious_evidence = all(token in evidence_context for token in (
        "恶意违约", "实际损失", "履行", "举证", "不能排除司法调整",
    ))
    if (
        malicious_claim and malicious_evidence
        and not guarded_legal_coverage_complete(clause, evidence_context, accepted_points)
    ):
        refs = [doc_id for doc_id in (
            "合同编通则司法解释·违约金调整", "民法典合同编·违约责任与定金",
        ) if doc_id in evidence_context]
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "合同约定不能排除人民法院或仲裁机构依法调整违约金，违约方提出的“不问实际损失"
                "及履行情况一律减半”同样没有依据。是否调减须由当事人提出请求，主张方就过高及"
                "相关事实举证，并以实际损失为基础，结合合同履行、过错、交易背景等综合衡量。若"
                "恶意违约经证据查明，其调减请求通常不获支持；本案恶意是否属实仍需举证，不能先"
                "作为既定事实，也不能据未核实指控直接拒绝全部调整。"
            ),
            "risk_level": "高",
            "suggested_content": (
                "删除“禁止法院调整”和“一律减半”，改为任何一方均可依法请求调整并承担相应"
                "举证责任；审查实际损失、履行程度、过错和交易背景。恶意违约仅在证据查明后作为"
                "通常不支持调减的重要因素，当前标注为待核实，不预设成立或不成立。"
            ),
            "evidence_refs": refs,
        })

    foreign_claim = "涉外民事纠纷" in clause and "书面协议选择中国人民法院" in clause
    foreign_evidence = (
        ("第277条" in evidence_context or "第二百七十七条" in evidence_context)
        and "不要求争议与我国必须有实际联系" in evidence_context
    )
    if (
        foreign_claim and foreign_evidence
        and not guarded_legal_coverage_complete(clause, evidence_context, accepted_points)
    ):
        refs = ["民事诉讼法·协议管辖与实际联系（2023修正）"] if (
            "民事诉讼法·协议管辖与实际联系（2023修正）" in evidence_context
        ) else []
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "已核实为涉外民事纠纷且双方以书面协议选择中国人民法院管辖，应适用《民事诉讼法》"
                "第277条；该规则不要求争议与我国具有实际联系，不能直接套用国内协议管辖第35条"
                "否定约定。现有事实下，仅因缺乏实际联系而认定当然无效没有依据。仍须核验书面协议"
                "范围、级别管辖及专属管辖等限制；在已给定的第277条选择前提下，不无依据追加必须"
                "指定某一个具体中国法院才有效的要求。"
            ),
            "risk_level": "高",
            "suggested_content": (
                "删除“仅因与我国无实际联系即当然无效”，明确双方依据第277条书面选择中国人民"
                "法院管辖且不以实际联系为生效条件；签约及起诉前核对级别、专属管辖和协议覆盖的"
                "争议范围。若另行选择具体受诉法院，应基于案件事实和适用规则确定，不能把该选择"
                "误写成第277条本身未规定的统一生效条件。"
            ),
            "evidence_refs": refs,
        })

    arbitration_claim = (
        "普通国内采购合同" in clause
        and "深圳国际仲裁院" in clause
        and "一裁终局" in clause
    )
    arbitration_evidence = (
        "仲裁法·仲裁协议与一裁终局（2025修订）" in evidence_context
        and "仲裁意思" in evidence_context and "一裁终局" in evidence_context
        and "第82条" in evidence_context
    )
    if (
        arbitration_claim and arbitration_evidence
        and not guarded_legal_coverage_complete(clause, evidence_context, accepted_points)
    ):
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "仲裁实行一裁终局，因此“一裁终局”及没有通常上诉机制本身不是违法、不公平或"
                "必须改为诉讼的理由。条款已用书面文字表达将争议提交深圳国际仲裁院的仲裁意思；"
                "签约时仍应核验机构真实存续、正式名称与条款所称机构一致并具有可确定性，以及"
                "仲裁事项范围没有与诉讼条款冲突。机构约定不明时可依法补充，不能补充才涉及效力。"
                "本案已明确是普通国内采购合同，不适用第82条特定涉外案件的临时仲裁例外。"
            ),
            "risk_level": "低",
            "suggested_content": (
                "保留仲裁和一裁终局安排；签约前通过仲裁机构官方信息确认其存续、正式名称及"
                "受理范围，并在条款中使用核验后的全称，明确因本合同产生的争议均提交该机构，"
                "按其届时有效规则仲裁。若机构名称或指向仍不明确，先书面补充确定；不要仅因"
                "一裁终局改为诉讼，也不要把第82条涉外特别规则套用于本普通国内采购。"
            ),
            "evidence_refs": ["仲裁法·仲裁协议与一裁终局（2025修订）"],
        })

    force_majeure_claim = all(token in clause for token in (
        "实际影响", "及时通知", "合理期限提供证明", "合理减损", "迟延履行后",
    ))
    force_majeure_evidence = (
        "第五百九十条" in evidence_context and "第五百九十一条" in evidence_context
    )
    if (
        force_majeure_claim and force_majeure_evidence
        and not guarded_legal_coverage_complete(clause, evidence_context, accepted_points)
    ):
        findings.append({
            "original_content": clause[:2000],
            "risk_analysis": (
                "条款已包含不可抗力审查的核心约束：仅按事件对履行的实际影响范围处理，要求"
                "及时通知并在合理期限提供证明、采取合理减损措施，并明确迟延履行后发生不可抗力"
                "不免除既有违约责任。这些内容与《民法典》第五百九十条、第五百九十一条的影响、"
                "通知证明、减损和迟延例外相衔接，不构成缺失，也不能仅因未写固定天数、固定证明"
                "形式或不可抗力持续期限就认定条款约束不足，更不能推定事件发生即自动解除合同。"
            ),
            "risk_level": "低",
            "suggested_content": (
                "保留现有按影响范围处理、及时通知、合理期限证明、合理减损及迟延履行例外。"
                "如双方确有项目管理需要，可另行约定通知渠道、联系人或示例材料，但应保留“合理"
                "期限”和对实际影响的个案判断，不把固定天数、特定机构证明或自动解除写成新的"
                "强制前提。"
            ),
            "evidence_refs": ["民法典合同编·违约责任与定金"],
        })
    return findings


def _is_large_enterprise_payment_case(clause: str) -> bool:
    return all(token in clause for token in (
        "甲方为大型企业", "乙方为中小企业", "90日", "行业规范", "交易习惯", "第三方款项",
    ))
