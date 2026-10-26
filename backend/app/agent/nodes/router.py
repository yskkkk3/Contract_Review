"""Router node: map each contract chunk to risk-dimension specialists.

策略（简历点）：LLM 批量分类为主 + 关键词规则兜底——对无法分类或
低置信的条款按规则引擎分配，保证每个条款至少有一个审阅维度。
"""
import json
import re

from app.agent.prompts import load_prompt
from app.agent.review_profiles import get_profile, matching_checks, profiled
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


@profiled()
async def router_node(state: ReviewState) -> dict:
    chunks = state["chunks"]
    llm_routes = await _llm_route(chunks) if len(chunks) <= 60 else None

    routed: list[dict] = []
    for idx, chunk in enumerate(chunks):
        dims = llm_routes.get(idx) if llm_routes else None
        if dims is None:
            dims = _rule_route(chunk)
        checks = matching_checks(state.get("contract_type", ""), chunk)
        dims = list(dict.fromkeys([*dims, *(check.risk_dim for check in checks)]))
        routed.append({
            "chunk_index": idx,
            "risk_dims": dims,
            "scope_dims": [],
            "scope_check_ids": {},
        })
    if routed:
        # Six shared dimensions remain present even when a topic has no keyword.
        # Every specialty check is assigned exactly once. Checks sharing a risk
        # dimension may belong to different clauses and must not be bundled blindly.
        for dim in RISK_DIMS:
            candidates = [item for item in routed if dim in item["risk_dims"]]
            if not candidates:
                routed[0]["risk_dims"].append(dim)
        profile = get_profile(state.get("contract_type"))
        if profile.key != "common":
            for check in profile.checks:
                candidates = [item for item in routed if check.risk_dim in item["risk_dims"]]
                matched = [
                    item for item in candidates
                    if check in matching_checks(profile.name, chunks[item["chunk_index"]], check.risk_dim)
                ]
                target = (matched or candidates or routed)[0]
                target["scope_check_ids"].setdefault(check.risk_dim, []).append(check.id)
                if check.risk_dim not in target["scope_dims"]:
                    target["scope_dims"].append(check.risk_dim)
    return {"routed": routed}
