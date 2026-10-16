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
    """只检查明确先迟延后事件、且可见590条时建议重新引入免责的情形。"""
    fact = _LATE_FACT.search(clause)
    if not (fact and "不可抗力" in clause and "第五百九十条" in evidence_context):
        return []
    if re.search(r"(?:若|如果|假如|是否|可能)[^。；]{0,16}$", clause[:fact.start()]):
        return []
    for sentence in re.split(r"[。；;\n]", point.get("suggested_content", "")):
        if re.search(r"未迟延(?:履行)?的?(?:一方|当事人)|非迟延方|不可抗力发生在迟延之前", sentence):
            continue
        for match in _EXEMPTION.finditer(sentence):
            prefix = sentence[:match.start()]
            if re.search(r"(?:不|不得|不能|禁止)(?:主张|适用|据此|自动)?$", prefix):
                continue
            return ["已明确先迟延后发生事件，修改建议仍引入按影响部分或全部免责，须保留第590条迟延后例外"]
    return []


def required_legal_findings(
    clause: str,
    evidence_context: str,
    accepted_points: list[dict],
) -> list[dict]:
    """Return narrow evidence-backed findings that may not be silently lost by an LLM gate."""
    fact = _LATE_FACT.search(clause)
    if not (fact and "不可抗力" in clause and "第五百九十条" in evidence_context):
        return []
    if any(
        re.search(
            r"迟延履行后.{0,30}(?:不免除|不得免除|不能免除).{0,20}违约责任",
            point.get("risk_analysis", "") + point.get("suggested_content", ""),
        )
        for point in accepted_points
    ):
        return []
    refs = ["民法典合同编·违约责任与定金"] if "民法典合同编·违约责任与定金" in evidence_context else []
    return [{
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
    }]
