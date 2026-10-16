"""Gate node: quality check (format / missing fields / hallucination guard).

简历点：LLM 质检 + 规则校验双层；不合格结果触发一次纠错重试。
"""
import json

from app.agent.prompts import load_prompt
from app.agent.rules.legal_guards import legal_conclusion_errors
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


def _rule_check(point: dict, chunk: str | None = None) -> list[str]:
    errors: list[str] = []
    if not point.get("original_content", "").strip():
        errors.append("original_content 为空")
    elif chunk is not None and point["original_content"] not in chunk:
        errors.append("original_content 不是当前条款的连续原文")
    if point.get("risk_level") not in VALID_LEVELS:
        errors.append("risk_level 非法")
    if not point.get("risk_analysis", "").strip():
        errors.append("risk_analysis 为空")
    if not point.get("suggested_content", "").strip():
        errors.append("suggested_content 为空")
    return errors


async def _llm_check(point: dict, chunk: str, evidence_context: str = "") -> bool:
    try:
        prompt = load_prompt("gate")
        data = await get_sf_client().chat_structured(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps({
                    "clause": chunk, "risk_point": point, "evidence_context": evidence_context,
                }, ensure_ascii=False)},
            ],
            json_schema=GATE_SCHEMA,
            model=settings.llm_review_model,
            temperature=0,
            max_tokens=256,
        )
        return isinstance(data, dict) and data.get("valid") is True
    except Exception:  # noqa: BLE001
        return False


async def _retry_fix(point: dict, chunk: str, risk_dim: str, evidence_context: str = "", issues: list[str] | None = None) -> dict | None:
    """纠错重试：把质检错误反馈给 LLM 重新生成。"""
    try:
        sf = get_sf_client()
        raw = await sf.chat(
            [
                {"role": "system", "content": load_prompt("gate_repair")},
                {"role": "user", "content": json.dumps({
                    "clause": chunk, "risk_dim": risk_dim, "previous": point,
                    "evidence_context": evidence_context,
                    "issues": issues or [],
                }, ensure_ascii=False)},
            ],
            model=settings.llm_review_model,
            temperature=0,
            max_tokens=1024,
            brief=True,
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
    errors = list(state.get("errors", []))
    for output in state["specialist_outputs"]:
        for point in output.get("result", []):
            chunk = state["chunks"][output["chunk_index"]]
            evidence_context = output.get("evidence_context", "")
            point_errors = _rule_check(point, chunk) + legal_conclusion_errors(point, chunk, evidence_context)
            llm_ok = not point_errors and await _llm_check(point, chunk, evidence_context)
            if point_errors or not llm_ok:
                # 纠错重试一次
                fixed = await _retry_fix(point, chunk, output["risk_dim"], evidence_context, point_errors)
                if (fixed and not _rule_check(fixed, chunk)
                        and not legal_conclusion_errors(fixed, chunk, evidence_context)
                        and await _llm_check(fixed, chunk, evidence_context)):
                    # 修复阶段没有重新检索，不能凭空增加未经专家阶段核验的引用。
                    refs = fixed.get("evidence_refs", [])
                    allowed = point.get("evidence_refs", [])
                    fixed["evidence_refs"] = [
                        ref for ref in refs if isinstance(ref, str) and ref in allowed
                    ] if isinstance(refs, list) else []
                    point = fixed
                else:
                    errors.append(f"条款{output['chunk_index']}部分意见未通过证据与事实核验")
                    continue
            point["risk_dim"] = output["risk_dim"]
            point["chunk_index"] = output["chunk_index"]
            gated.append(point)
            # 只流式展示已核验结果，避免已被质检剔除的法律结论仍留在前端。
            try:
                from langgraph.config import get_stream_writer

                get_stream_writer()({"type": "risk_point", "risk_dim": output["risk_dim"], "points": [point]})
            except Exception:  # noqa: BLE001 非流式上下文兼容
                pass
    return {"gated": gated, "errors": errors}
