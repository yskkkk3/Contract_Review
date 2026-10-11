"""确定性风险规则引擎：6 个风险维度的规则化 Skills。

设计：规则函数（纯 Python，无 LLM）对条款文本做模式匹配，输出与专家结果同构的
风险点（original_content / risk_analysis / risk_level / suggested_content / risk_dim）。
与 LLM 专家结果合并，增强召回率与可解释性（简历点：LLM + 规则双引擎）。
"""
from __future__ import annotations

import re


def _make(original, analysis, level, suggestion, risk_dim):
    return {"original_content": original, "risk_analysis": analysis,
            "risk_level": level, "suggested_content": suggestion, "risk_dim": risk_dim}


# ---- 主体资格与合规 ----
def rule_party_identity(text: str) -> list[dict]:
    out = []
    if "甲方" in text and "乙方" in text and "统一社会信用代码" not in text and "信用代码" not in text:
        out.append(_make(text[:200], "合同未提供双方统一社会信用代码等主体信息，存在主体资格核验缺口", "中",
                         "补充甲乙双方名称、统一社会信用代码、住所等主体信息", "主体资格与合规"))
    return out


# ---- 财务与付款 ----
_PREPAY_RE = re.compile(r"预付款[^%0-9]{0,12}(\d+)\s*%|支付.*?(\d+)\s*%")
def rule_prepayment_ratio(text: str) -> list[dict]:
    m = _PREPAY_RE.search(text)
    if m:
        pct = int(m.group(1) or m.group(2))
        if pct > 30:
            return [_make(text[:200], f"预付款比例 {pct}% 超过采购惯例上限 30%，资金占用与供应商违约风险偏高", "高",
                          "将预付款比例降至 30% 以内或补充履约担保", "财务与付款")]
    return []


def rule_amount_consistency(text: str) -> list[dict]:
    if ("价款" in text or "金额" in text) and "人民币" in text and "大小写" not in text:
        return [_make(text[:200], "价款条款未见大小写金额一致性表述，存在结算歧义风险", "中",
                      "同时注明大写与小写金额并保持一致", "财务与付款")]
    return []


# ---- 知识产权与保密 ----
def rule_ip_ownership(text: str) -> list[dict]:
    if ("开发" in text or "成果" in text or "源代码" in text) and "知识产权" not in text:
        return [_make(text[:200], "涉及开发/成果条款但未约定知识产权归属，存在权属争议风险", "高",
                      "明确约定成果知识产权归属（高校惯例归学校）", "知识产权与保密")]
    return []


def rule_confidentiality(text: str) -> list[dict]:
    if "保密" in text and "期限" not in text and "范围" not in text:
        return [_make(text[:200], "保密条款未明确保密范围与期限，可执行性不足", "中",
                      "补充保密范围、保密期限与违约后果", "知识产权与保密")]
    return []


# ---- 违约责任与解除 ----
def rule_penalty_base(text: str) -> list[dict]:
    if "违约金" in text and ("基数" not in text and "合同总额" not in text and "未付金额" not in text and "已付金额" not in text):
        return [_make(text[:200], "违约金计算基数不明确（合同总额 vs 未付金额），执行易生争议", "中",
                      "明确违约金计算基数（如未付金额）", "违约责任与解除")]
    return []


# ---- 验收交付与质保 ----
def rule_acceptance_standard(text: str) -> list[dict]:
    if ("验收" in text) and ("标准" not in text and "依据" not in text and "附件" not in text):
        return [_make(text[:200], "验收条款未明确验收标准/依据，验收缺乏客观尺度", "高",
                      "明确验收标准、验收方法与时限（可引用附件）", "验收交付与质保")]
    return []


# ---- 争议解决与管辖 ----
def rule_arbitration_final(text: str) -> list[dict]:
    if "仲裁" in text and "终局" in text:
        return [_make(text[:200], "约定仲裁且一裁终局，对高校方丧失上诉救济机会，需权衡保密性/成本", "中",
                      "确认仲裁机构明确；若争议金额大可评估诉讼管辖", "争议解决与管辖")]
    return []


_RULES: list[tuple[str, object]] = [
    ("主体资格与合规", rule_party_identity),
    ("财务与付款", rule_prepayment_ratio),
    ("财务与付款", rule_amount_consistency),
    ("知识产权与保密", rule_ip_ownership),
    ("知识产权与保密", rule_confidentiality),
    ("违约责任与解除", rule_penalty_base),
    ("验收交付与质保", rule_acceptance_standard),
    ("争议解决与管辖", rule_arbitration_final),
]


def apply_rules(text: str, risk_dim: str) -> list[dict]:
    """对单个条款文本应用指定维度的规则，返回命中的风险点列表。"""
    out = []
    for dim, fn in _RULES:
        if dim != risk_dim:
            continue
        try:
            out.extend(fn(text))
        except Exception:  # noqa: BLE001  规则失败不影响主流程
            continue
    return out


def apply_all_rules(chunks: list[str]) -> list[dict]:
    """对全部条款块应用所有维度规则（用于仲裁后合并）。"""
    out = []
    for chunk in chunks:
        for _dim, fn in _RULES:
            try:
                out.extend(fn(chunk))
            except Exception:  # noqa: BLE001
                continue
    return out
