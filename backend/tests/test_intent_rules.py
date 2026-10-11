"""意图规则引擎评测：混淆样本集 + 边界 case（确定性、无 LLM 依赖）。"""
from __future__ import annotations

import pytest

from app.agent.rules.intent_rules import rule_classify

# 混淆样本集（intent eval set）：覆盖强关键词、否定词降权、组合规则、同分仲裁
EVAL_CASES: list[tuple[str, str]] = [
    # --- review ---
    ("帮我审阅这份合同的风险", "review"),
    ("这个合同要审查吗", "review"),
    ("合同里付款条款有什么问题", "review"),
    ("审一下采购合同", "review"),
    ("帮我看看合同哪些条款违规", "review"),
    # --- compare ---
    ("对比这两份合同有什么差异", "compare"),
    ("两版合同对比一下再定", "compare"),
    ("比对 A、B 两份合同的区别", "compare"),
    # --- admin ---
    ("配置一下提示词", "admin"),
    ("合同模板管理", "admin"),
    ("修改模型配置", "admin"),
    # --- chat ---
    ("什么是质保金", "chat"),
    ("解释一下违约金条款", "chat"),
    ("为什么要有履约保证金", "chat"),
    # --- 否定词降权 ---
    ("不用审阅，直接解释一下违约金条款", "chat"),
    ("无需对比，简单看看就行", "chat"),
    ("别审查了，说说怎么付款", "chat"),
]


def test_eval_set_accuracy():
    """混淆样本集全量通过率（门禁口径：>= 13/15，当前期望 100%）。"""
    passed = 0
    failures = []
    for text, expected in EVAL_CASES:
        intent, _conf, _matched = rule_classify(text)
        if intent == expected:
            passed += 1
        else:
            failures.append((text, expected, intent))
    assert passed >= 13, f"准确率过低 {passed}/{len(EVAL_CASES)}: {failures}"
    assert not failures


def test_negation_verb_resets_intent():
    intent, conf, matched = rule_classify("不用审阅，直接解释一下违约金条款")
    assert intent == "chat"
    assert "解释" in matched
    # 强规则命中但被否定词清零 → 置信度不会很高
    assert conf <= 0.5


def test_strong_rule_priority():
    intent, conf, _ = rule_classify("帮我审阅这份合同的风险")
    assert intent == "review"
    assert conf >= 0.9  # 强关键词（审阅 权重3）→ 高置信


def test_composite_rule():
    intent, _conf, _ = rule_classify("合同里付款条款有什么问题")
    assert intent == "review"


def test_fallback_default():
    intent, conf, matched = rule_classify("今天天气怎么样")
    assert intent == "chat"
    assert conf <= 0.3  # "怎么" 普通词命中 → 低置信


@pytest.mark.parametrize(
    "text,intent",
    [
        ("审阅", "review"),
        ("对比", "compare"),
        ("配置", "admin"),
        ("解释", "chat"),
    ],
)
def test_single_keyword(text, intent):
    assert rule_classify(text)[0] == intent
