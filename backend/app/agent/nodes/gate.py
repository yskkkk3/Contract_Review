"""Gate node: quality check (format / missing fields / hallucination guard).

简历点：LLM 质检 + 规则校验双层；不合格结果触发一次纠错重试。
"""
import json
import re

from app.agent.prompts import load_prompt
from app.agent.review_profiles import profiled
from app.agent.rules.legal_guards import (
    guarded_legal_coverage_complete,
    legal_conclusion_errors,
    required_legal_findings,
)
from app.agent.state import ReviewState
from app.core.config import get_settings
from app.rag.client import LLMOutputTruncated, get_sf_client, is_provider_unavailable_error

settings = get_settings()

VALID_LEVELS = {"高", "中", "低"}

GATE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["accept", "drop", "revise"]},
        "issues": {
            "type": "array", "maxItems": 4,
            "items": {"type": "string", "maxLength": 200},
        },
    },
    "required": ["decision", "issues"],
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


def _canonical_source(
    original: str,
    chunks: list[str],
    preferred_index: int,
) -> tuple[int, str]:
    """Map whitespace-normalized/tool-read quotations back to exact contract text."""
    if not original:
        return preferred_index, original
    order = [preferred_index, *(index for index in range(len(chunks)) if index != preferred_index)]
    for index in order:
        chunk = chunks[index]
        if original in chunk:
            return index, original

    candidates = [original]
    without_item_number = re.sub(r"^\s*\d+\s*[.．、]\s*", "", original, count=1)
    if without_item_number != original:
        candidates.append(without_item_number)
    for candidate in candidates:
        compact_original = "".join(char for char in candidate if not char.isspace())
        if not compact_original:
            continue
        for index in order:
            chunk = chunks[index]
            positions = [position for position, char in enumerate(chunk) if not char.isspace()]
            compact_chunk = "".join(chunk[position] for position in positions)
            start = compact_chunk.find(compact_original)
            if start >= 0:
                first = positions[start]
                last = positions[start + len(compact_original) - 1] + 1
                return index, chunk[first:last]
    return preferred_index, original


async def _llm_check(
    point: dict,
    chunk: str,
    evidence_context: str = "",
    accepted_points: list[dict] | None = None,
) -> dict | bool:
    try:
        prompt = load_prompt("gate")
        data = await get_sf_client().chat_structured(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps({
                    "clause": chunk, "risk_point": point, "evidence_context": evidence_context,
                    "accepted_risk_points": accepted_points or [],
                }, ensure_ascii=False)},
            ],
            model_type="review", json_schema=GATE_SCHEMA,
            model=settings.llm_review_model,
            temperature=0,
            max_tokens=1024,
        )
        if isinstance(data, dict) and data.get("decision") in {"accept", "drop", "revise"}:
            issues = data.get("issues", [])
            if isinstance(issues, list) and all(isinstance(item, str) for item in issues):
                return {"decision": data["decision"], "issues": issues}
        # Keep compatibility with cached/test responses from the former boolean schema.
        if isinstance(data, dict) and isinstance(data.get("valid"), bool):
            return data["valid"]
        return False
    except Exception as exc:  # noqa: BLE001
        if is_provider_unavailable_error(exc) or isinstance(exc, LLMOutputTruncated):
            raise
        return False


def _normalize_assessment(value: dict | bool) -> tuple[str, list[str]]:
    if value is True:
        return "accept", []
    if isinstance(value, dict) and value.get("decision") in {"accept", "drop", "revise"}:
        return value["decision"], list(value.get("issues", []))
    return "revise", ["模型质检未返回有效分类"]


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
    except Exception as exc:
        if is_provider_unavailable_error(exc) or isinstance(exc, LLMOutputTruncated):
            raise
        return None


@profiled()
async def gate_node(state: ReviewState) -> dict:
    gated: list[dict] = []
    errors = list(state.get("errors", []))
    generation_failure: Exception | None = None

    async def paid_check(operation, *args):
        nonlocal generation_failure
        try:
            return await operation(*args)
        except Exception as exc:
            if not (is_provider_unavailable_error(exc) or isinstance(exc, LLMOutputTruncated)):
                raise
            generation_failure = exc
            return None

    for output in state["specialist_outputs"]:
        accepted_for_output: list[dict] = []
        unresolved_structure_failure = False
        unresolved_legal_failure = False
        gate_unavailable = False
        for point in output.get("result", []):
            if generation_failure is not None:
                gate_unavailable = True
                break
            point = dict(point)
            point_chunk_index, canonical = _canonical_source(
                point.get("original_content", ""), state["chunks"], output["chunk_index"],
            )
            point["original_content"] = canonical
            chunk = state["chunks"][point_chunk_index]
            evidence_context = output.get("evidence_context", "")
            structure_errors = _rule_check(point, chunk)
            legal_errors = legal_conclusion_errors(point, chunk, evidence_context)
            point_errors = structure_errors + legal_errors
            if point_errors:
                decision, assessment_issues = "revise", []
            else:
                decision, assessment_issues = _normalize_assessment(
                    await paid_check(_llm_check, point, chunk, evidence_context, accepted_for_output)
                )
            if generation_failure is not None:
                gate_unavailable = True
                break
            if decision == "drop" and not point_errors:
                # A sound clause or a purely optional improvement is not a reportable risk.
                continue
            if point_errors or decision != "accept":
                # 纠错重试一次
                issues = point_errors + assessment_issues
                fixed = await paid_check(_retry_fix, point, chunk, output["risk_dim"], evidence_context, issues)
                if generation_failure is not None:
                    gate_unavailable = True
                    break
                fixed_errors = (
                    _rule_check(fixed, chunk) + legal_conclusion_errors(fixed, chunk, evidence_context)
                    if fixed else ["修复未返回有效风险点"]
                )
                fixed_decision, _ = (
                    _normalize_assessment(
                        await paid_check(_llm_check, fixed, chunk, evidence_context, accepted_for_output)
                    )
                    if fixed and not fixed_errors else ("revise", [])
                )
                if generation_failure is not None:
                    gate_unavailable = True
                    break
                if fixed and not fixed_errors and fixed_decision == "accept":
                    # 修复阶段没有重新检索，不能凭空增加未经专家阶段核验的引用。
                    refs = fixed.get("evidence_refs", [])
                    allowed = point.get("evidence_refs", [])
                    fixed["evidence_refs"] = [
                        ref for ref in refs if isinstance(ref, str) and ref in allowed
                    ] if isinstance(refs, list) else []
                    point = fixed
                elif fixed and not point_errors and fixed_decision == "drop":
                    continue
                else:
                    # A valid LLM gate can safely filter its own rejected candidate. A hard rule
                    # failure, or an unavailable gate, still marks the review incomplete unless a
                    # deterministic evidence-backed finding replaces that exact guarded issue.
                    if structure_errors:
                        unresolved_structure_failure = True
                    if legal_errors:
                        unresolved_legal_failure = True
                    elif assessment_issues == ["模型质检未返回有效分类"]:
                        gate_unavailable = True
                    continue
            point["risk_dim"] = output["risk_dim"]
            point["chunk_index"] = point_chunk_index
            gated.append(point)
            accepted_for_output.append(point)
            # 只流式展示已核验结果，避免已被质检剔除的法律结论仍留在前端。
            try:
                from langgraph.config import get_stream_writer

                get_stream_writer()({"type": "risk_point", "risk_dim": output["risk_dim"], "points": [point]})
            except Exception:  # noqa: BLE001 非流式上下文兼容
                pass
        chunk = state["chunks"][output["chunk_index"]]
        evidence_context = output.get("evidence_context", "")
        protected = required_legal_findings(chunk, evidence_context, accepted_for_output)
        for point in protected:
            point["risk_dim"] = output["risk_dim"]
            point["chunk_index"] = output["chunk_index"]
            gated.append(point)
            try:
                from langgraph.config import get_stream_writer

                get_stream_writer()({
                    "type": "risk_point", "risk_dim": output["risk_dim"], "points": [point],
                })
            except Exception:  # noqa: BLE001 非流式上下文兼容
                pass
        critical_coverage_complete = bool(protected) or guarded_legal_coverage_complete(
            chunk, evidence_context, accepted_for_output + protected,
        )
        if (unresolved_structure_failure
                or ((gate_unavailable or unresolved_legal_failure)
                    and not critical_coverage_complete)):
            errors.append(f"条款{output['chunk_index']}部分意见未通过证据与事实核验")
    if generation_failure is not None:
        reason = "质检模型输出被截断" if isinstance(generation_failure, LLMOutputTruncated) else "质检模型暂不可用"
        errors.append(f"{reason}，已停止后续模型修复；当前审阅未完成（{type(generation_failure).__name__}）")
    return {"gated": gated, "errors": errors}
