"""Arbitration node: dedupe / conflict resolution / summary."""
import json

from app.agent.prompts import load_prompt
from app.agent.state import ReviewState
from app.core.config import get_settings
from app.rag.client import get_sf_client

settings = get_settings()

SUMMARY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "审阅总结"},
        "suggestion": {"type": "string", "description": "修改建议"},
        "overall_risk": {"type": "string", "enum": ["高", "中", "低"]},
    },
    "required": ["summary", "suggestion", "overall_risk"],
    "additionalProperties": False,
}


def _arbitrate_rules(points: list[dict], chunks: list[str] | None = None) -> list[dict]:
    """按 chunk_index 排序 + 同条款风险合并（取最高等级）。"""
    merged: dict[int, dict] = {}
    for p in points:
        idx = p.get("chunk_index", 0)
        if idx not in merged:
            merged[idx] = {
                "index": idx,
                "original_content": p["original_content"],
                "risk_analysis": p["risk_analysis"],
                "risk_level": p["risk_level"],
                "suggested_content": p["suggested_content"],
                "risk_dim": p.get("risk_dim", ""),
                "evidence_refs": p.get("evidence_refs", []),
                "dim_count": 1,
            }
        else:
            prev = merged[idx]
            # 合并分析，取最高等级
            prev["risk_analysis"] = f"{prev['risk_analysis']}\n[{p.get('risk_dim','')}] {p['risk_analysis']}"
            if p["suggested_content"] not in prev["suggested_content"]:
                prev["suggested_content"] += f"\n[{p.get('risk_dim','')}] {p['suggested_content']}"
            if p["original_content"] not in prev["original_content"]:
                prev["original_content"] += "\n" + p["original_content"]
            if {"高": 3, "中": 2, "低": 1}[p["risk_level"]] > {"高": 3, "中": 2, "低": 1}[prev["risk_level"]]:
                prev["risk_level"] = p["risk_level"]
            prev["evidence_refs"] = list(
                dict.fromkeys((prev.get("evidence_refs") or []) + (p.get("evidence_refs") or []))
            )[:5]
            prev["dim_count"] += 1
    result = [merged[k] for k in sorted(merged)]
    if chunks:
        for point in result:
            index = point["index"]
            if 0 <= index < len(chunks) and point["original_content"] not in chunks[index]:
                # 多项原文摘录合并时保留完整源条款，不能制造并不存在的连续原文。
                point["original_content"] = chunks[index]
    return result


def _overall_risk(points: list[dict]) -> str:
    rank = {"低": 1, "中": 2, "高": 3}
    return max((point["risk_level"] for point in points), key=lambda level: rank[level], default="低")


async def _llm_summary(points: list[dict], stance: str) -> dict:
    try:
        prompt = load_prompt("arbitration", stance=stance)
        data = await get_sf_client().chat_structured(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(points, ensure_ascii=False)},
            ],
            model_type="review", json_schema=SUMMARY_SCHEMA,
            model=settings.llm_review_model,
            temperature=0.2,
            max_tokens=512,
        )
        if data:
            return {
                "summary": str(data.get("summary", "")),
                "suggestion": str(data.get("suggestion", "")),
                "overall_risk": data.get("overall_risk", "低") if data.get("overall_risk") in {"高", "中", "低"} else "低",
            }
    except Exception:  # noqa: BLE001
        pass
    risk = _overall_risk(points)
    return {
        "summary": f"共发现 {len(points)} 个潜在风险点，整体风险等级为 {risk}。",
        "suggestion": f"建议重点关注高风险条款，并根据 {stance} 立场调整合同文本。",
        "overall_risk": risk,
    }


async def arbitration_node(state: ReviewState) -> dict:
    if state.get("intent") not in (None, "review"):
        state = {**state, "errors": [*state.get("errors", []), "审阅流程未执行"]}
    points = _arbitrate_rules(state["gated"], state.get("chunks"))
    summary = await _llm_summary(points, state["stance"])
    summary["overall_risk"] = _overall_risk(points)
    summary["review_status"] = "incomplete" if state.get("errors") else "completed"
    if state.get("errors"):
        summary["summary"] = (
            "本次存在关键证据缺口或部分意见未能核验，尚未形成完整审阅结论；"
            "未输出风险不代表合同无风险。已核验风险点仅供当前材料范围内参考。"
        )
        summary["suggestion"] = "请先补查相关规则、适用条件及合同材料，并重新复核；当前材料不能支持直接签订的结论。"
    return {"final_risk_points": points, "summary": summary}
