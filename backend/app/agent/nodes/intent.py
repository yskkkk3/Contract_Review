"""Intent classifier node: structured output classification + rule-based fallback.

简历点：混合路由——LLM 主分类（OpenAI structured output json_schema，解析稳定），
解析失败/低置信时降级到独立规则引擎（app/agent/rules/intent_rules.py：强关键词、
组合规则、否定词降权、同分仲裁），再兜底默认意图，保证路由 100% 可达。
"""
from app.agent.prompts import load_prompt
from app.agent.rules.intent_rules import rule_classify
from app.agent.state import ReviewState
from app.core.config import get_settings
from app.rag.client import get_sf_client

settings = get_settings()

INTENT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["review", "compare", "chat", "admin"]},
        "confidence": {"type": "number", "description": "0-1 置信度"},
    },
    "required": ["intent", "confidence"],
    "additionalProperties": False,
}


def _rule_classify(text: str) -> tuple[str, float]:
    # 独立规则引擎：确定性、可评测（tests/test_intent_rules.py）
    intent, confidence, _matched = rule_classify(text)
    return intent, confidence


async def _llm_classify(text: str) -> tuple[str, float] | None:
    try:
        prompt = load_prompt("intent")
        data = await get_sf_client().chat_structured(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"用户请求：{text[:2000]}"},
            ],
            json_schema=INTENT_SCHEMA,
            model=settings.llm_intent_model,
            temperature=0,
            max_tokens=256,
        )
        if not data:
            return None
        intent = data.get("intent")
        if intent not in {"review", "compare", "chat", "admin"}:
            return None
        confidence = float(data.get("confidence", 0.0))
        return intent, confidence
    except Exception:  # noqa: BLE001
        return None


async def intent_node(state: ReviewState) -> dict:
    """审阅任务入口：请求描述/意图确认。默认 review，识别失败走规则降级。"""
    text = state.get("description") or f"{state.get('contract_type', '')}合同审阅"
    intent, confidence = "review", 1.0

    if text:
        llm_result = await _llm_classify(text)
        if llm_result and llm_result[1] >= 0.5:
            intent, confidence = llm_result
        else:
            # 规则降级
            rule_intent, rule_conf = _rule_classify(text)
            if llm_result and llm_result[0] == "review":
                intent = "review"
            else:
                intent, confidence = rule_intent, rule_conf

    return {"intent": intent, "intent_confidence": confidence, "errors": []}
