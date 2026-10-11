"""Gate node: quality check (format / missing fields / hallucination guard).

简历点：LLM 质检 + 规则校验双层；不合格结果触发一次纠错重试。
"""
import json

from app.agent.prompts import load_prompt
from app.agent.state import ReviewState
from app.core.config import get_settings
from app.rag.client import get_sf_client

settings = get_settings()

VALID_LEVELS = {"高", "中", "低"}

GATE_SCHEMA: dict = {
    "type": "object",
    "properties": {"valid": {"type": "boolean", "description": "结果是否通过质检"}},
    "required": ["valid"],
    "additionalProperties": False,
}


def _rule_check(point: dict) -> list[str]:
    errors: list[str] = []
    if not point.get("original_content", "").strip():
        errors.append("original_content 为空")
    if point.get("risk_level") not in VALID_LEVELS:
        errors.append("risk_level 非法")
    if not point.get("risk_analysis", "").strip():
        errors.append("risk_analysis 为空")
    if not point.get("suggested_content", "").strip():
        errors.append("suggested_content 为空")
    return errors


async def _llm_check(point: dict) -> bool:
    try:
        prompt = load_prompt("gate")
        data = await get_sf_client().chat_structured(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(point, ensure_ascii=False)},
            ],
            json_schema=GATE_SCHEMA,
            model=settings.llm_intent_model,
            temperature=0,
            max_tokens=128,
        )
        return bool(data and data.get("valid", True) is True)
    except Exception:  # noqa: BLE001
        return True


async def _retry_fix(point: dict, chunk: str, risk_dim: str) -> dict | None:
    """纠错重试：把质检错误反馈给 LLM 重新生成。"""
    try:
        sf = get_sf_client()
        raw = await sf.chat(
            [
                {"role": "system", "content": "你是合同审阅结果修复器。根据质检错误修正输出，保持 JSON 结构不变。"},
                {"role": "user", "content": f"条款：{chunk[:500]}\n维度：{risk_dim}\n上次输出：{json.dumps(point, ensure_ascii=False)}\n请修正。"},
            ],
            model=settings.llm_review_model,
            temperature=0,
            max_tokens=1024,
        )
        import re

        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        fixed = json.loads(match.group(0))
        if fixed.get("original_content") and fixed.get("risk_level") in VALID_LEVELS:
            return fixed
        return None
    except Exception:
        return None


async def gate_node(state: ReviewState) -> dict:
    gated: list[dict] = []
    for output in state["specialist_outputs"]:
        for point in output.get("result", []):
            errors = _rule_check(point)
            llm_ok = await _llm_check(point)
            if errors or not llm_ok:
                # 纠错重试一次
                fixed = await _retry_fix(point, state["chunks"][output["chunk_index"]], output["risk_dim"])
                if fixed and not _rule_check(fixed):
                    point = fixed
                else:
                    if errors:
                        state.setdefault("errors", []).append(f"gate reject: {errors}")
                    continue
            point["risk_dim"] = output["risk_dim"]
            point["chunk_index"] = output["chunk_index"]
            gated.append(point)
    return {"gated": gated}
