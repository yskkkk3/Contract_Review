"""Rule-based intent classifier —— LLM 结构化分类的确定性降级策略。

设计要点（简历可讲）：
- 分层规则：强关键词（直接判定）＞ 组合规则（跨词共现）＞ 计分排序 ＞ 默认 chat；
- 否定词降权："不用审阅 / 无需对比" 类表达对 review/compare 计分扣减，避免误判；
- 同分仲裁：强规则命中数 → 关键词总长（信息量）→ 预定义意图顺序，保证输出确定；
- 纯函数、无外部依赖，可单测、可评测（tests/test_intent_rules.py 带混淆样本集）；
- 输出 (intent, confidence, matched) 供日志/可观测复现判定依据。
"""
from __future__ import annotations

RULE_FALLBACK_INTENT = "chat"

# (关键词, 权重)：权重 >=2 视为强关键词（直接命中即优先）
_INTENT_KEYWORDS: dict[str, list[tuple[str, int]]] = {
    "review": [
        ("审阅", 3),
        ("审查合同", 3),
        ("风险评估", 3),
        ("审查", 3),
        ("风险", 2),
        ("审一下", 2),
        ("把关", 2),
        ("修改建议", 2),
        ("合法", 1),
        ("合规", 1),
        ("条款问题", 1),
        ("违规", 1),
    ],
    "compare": [
        ("比对", 3),
        ("对比", 3),
        ("比较", 2),
        ("差异", 2),
        ("区别", 2),
        ("哪个更好", 2),
        ("两份合同", 2),
    ],
    "admin": [
        ("配置", 2),
        ("模型配置", 3),
        ("提示词", 2),
        ("prompt", 2),
        ("管理系统", 2),
        ("合同类型配置", 3),
        ("模板管理", 2),
    ],
    "chat": [
        ("问答", 1),
        ("咨询", 1),
        ("解释", 1),
        ("是什么", 1),
        ("为什么", 1),
        ("怎么", 1),
        ("介绍", 1),
        ("请问", 1),
    ],
}

# 否定词：命中时对 review/compare 计分扣减
_NEGATION_WORDS = ["不是", "不用", "无需", "别", "不要", "不必"]

# 否定词 + 动作动词共现（如"不用审阅"）：直接清零该意图，避免"不用审阅"误判为 review
_NEG_VERB_INTENT: dict[str, str] = {
    "审阅": "review",
    "审查": "review",
    "比对": "compare",
    "对比": "compare",
    "比较": "compare",
}

# 组合规则：跨词共现判定（比单关键词计分更强的信号）
_COMPOSITE_RULES: list[tuple[tuple[str, ...], str, int]] = [
    (("两个", "合同"), "compare", 3),  # "两个合同" 默认进入对比意图
    (("合同", "对比"), "compare", 3),
    (("对比", "条款"), "compare", 2),
    (("合同", "审阅"), "review", 3),
    (("条款", "问题"), "review", 2),  # "条款有什么问题" → 审阅意图
]

_INTENT_ORDER = ["review", "compare", "admin", "chat"]


def _score(text: str) -> dict[str, tuple[float, list[str]]]:
    """返回 {intent: (score, matched_keywords)}；含否定词降权与组合规则。"""
    lowered = text.lower()
    scores: dict[str, list[str]] = {i: [] for i in _INTENT_ORDER}
    for intent, kws in _INTENT_KEYWORDS.items():
        for kw, _weight in kws:
            if kw.lower() in lowered:
                scores[intent].append(kw)

    # 否定词 + 动作动词共现："不用审阅" 直接清零 review
    negated_intents: set[str] = set()
    for neg in _NEGATION_WORDS:
        idx = text.find(neg)
        if idx < 0:
            continue
        tail = text[idx + len(neg) : idx + len(neg) + 6]
        for verb, intent in _NEG_VERB_INTENT.items():
            if verb in tail:
                negated_intents.add(intent)

    # 权重化计分
    weighted: dict[str, float] = {}
    for intent, _m in scores.items():
        s = sum(w for kw, w in _INTENT_KEYWORDS[intent] if kw.lower() in lowered)
        if intent in negated_intents:
            s = 0.0
        elif intent in {"review", "compare"}:
            s -= sum(1 for w in _NEGATION_WORDS if w in text) * 0.5
        weighted[intent] = s

    for words, intent, w in _COMPOSITE_RULES:
        if all(kw in text for kw in words):
            weighted[intent] = max(weighted.get(intent, 0), w)

    return {
        i: (float(v), m)
        for i, v, m in zip(
            _INTENT_ORDER,
            [weighted[i] for i in _INTENT_ORDER],
            [scores[i] for i in _INTENT_ORDER],
            strict=True,
        )
    }


def rule_classify(text: str) -> tuple[str, float, list[str]]:
    """规则分类：返回 (intent, confidence, matched_keywords)。"""
    scored = _score(text or "")
    # 强规则（组合规则或强关键词 >=3）直接命中
    for intent in _INTENT_ORDER:
        score, matched = scored[intent]
        strong = any(kw.lower() in text.lower() and w >= 3 for kw, w in _INTENT_KEYWORDS[intent])
        if strong and score > 0 and not any(neg in text for neg in _NEGATION_WORDS if intent in {"review", "compare"}):
            return intent, min(0.95, 0.5 + score * 0.1), matched

    best_intent, best_score = RULE_FALLBACK_INTENT, -1.0
    best_matched: list[str] = []
    for intent in _INTENT_ORDER:
        score, matched = scored[intent]
        if score > best_score:
            best_intent, best_score, best_matched = intent, score, matched
        elif score == best_score and score > 0 and sum(len(k) for k in matched) > sum(len(k) for k in best_matched):
            # 同分仲裁：关键词总长（信息量更大者优先）
            best_intent, best_matched = intent, matched

    confidence = min(best_score * 0.2, 0.6) if best_score > 0 else 0.0
    if best_score <= 0:
        best_intent = RULE_FALLBACK_INTENT
    return best_intent, confidence, best_matched
