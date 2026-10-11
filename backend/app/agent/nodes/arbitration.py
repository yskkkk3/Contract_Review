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


def _arbitrate_rules(points: list[dict]) -> list[dict]:
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
            if {"高": 3, "中": 2, "低": 1}[p["risk_level"]] > {"高": 3, "中": 2, "低": 1}[prev["risk_level"]]:
                prev["risk_level"] = p["risk_level"]
            prev["evidence_refs"] = list(
                dict.fromkeys((prev.get("evidence_refs") or []) + (p.get("evidence_refs") or []))
            )[:5]
            prev["dim_count"] += 1
    return [merged[k] for k in sorted(merged)]


def _overall_risk(points: list[dict]) -> str:
    high = sum(1 for p in points if p["risk_level"] == "高")
    if high > 3 or len(points) > 10:
        return "高"
    if len(points) > 5:
        return "中"
    return "低"


async def _llm_summary(points: list[dict], stance: str) -> dict:
    try:
        prompt = load_prompt("arbitration", stance=stance)
        data = await get_sf_client().chat_structured(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(points, ensure_ascii=False)},
            ],
            json_schema=SUMMARY_SCHEMA,
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
    points = _arbitrate_rules(state["gated"])
    summary = await _llm_summary(points, state["stance"])
    return {"final_risk_points": points, "summary": summary}
