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
