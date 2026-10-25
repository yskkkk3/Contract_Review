"""Router node: map each contract chunk to risk-dimension specialists.

策略（简历点）：LLM 批量分类为主 + 关键词规则兜底——对无法分类或
低置信的条款按规则引擎分配，保证每个条款至少有一个审阅维度。
"""
import json
import re

from app.agent.prompts import load_prompt
from app.agent.state import RISK_DIM_KEYWORDS, RISK_DIMS, ReviewState
from app.core.config import get_settings
from app.rag.client import get_sf_client

settings = get_settings()


def _rule_route(chunk: str) -> list[str]:
    scored: dict[str, int] = {}
    for dim, keywords in RISK_DIM_KEYWORDS.items():
        scored[dim] = sum(1 for kw in keywords if kw in chunk)
    best = sorted(scored.items(), key=lambda x: x[1], reverse=True)
    dims = [dim for dim, score in best if score > 0][:2]
    return dims or ["主体资格与合规"]


async def _llm_route(chunks: list[str]) -> dict[int, list[str]] | None:
    try:
        prompt = load_prompt("router",
            dims="、".join(RISK_DIMS),
            chunks="\n".join(f"[{i}] {c[:200]}" for i, c in enumerate(chunks)),
        )
        raw = await get_sf_client().chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "请分发以上条款。"},
            ],
            model=settings.llm_intent_model, model_type="intent",
            temperature=0,
            max_tokens=2048,
        )
        data = json.loads(re.search(r"\[[\s\S]*\]", raw.strip()).group(0))
        result: dict[int, list[str]] = {}
        for item in data:
            idx = item.get("chunk_index")
            dims = item.get("risk_dims", [])
            if isinstance(idx, int) and 0 <= idx < len(chunks):
                result[idx] = [d for d in dims if d in RISK_DIMS] or ["主体资格与合规"]
        return result if result else None
    except Exception:
        return None


async def router_node(state: ReviewState) -> dict:
    chunks = state["chunks"]
    llm_routes = await _llm_route(chunks) if len(chunks) <= 60 else None

    routed: list[dict] = []
    for idx, chunk in enumerate(chunks):
        dims = llm_routes.get(idx) if llm_routes else None
        if dims is None:
            dims = _rule_route(chunk)
        routed.append({"chunk_index": idx, "risk_dims": dims})
    return {"routed": routed}
