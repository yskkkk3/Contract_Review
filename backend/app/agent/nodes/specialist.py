"""Specialist node: real ReAct loop with Function Calling tools.

流程（简历点）：
  1. 模型自主决定是否调用工具（search_regulations / get_clause / calc_penalty / lookup_template）；
  2. 工具结果作为 role="tool" 消息回喂，模型基于证据生成风险点；
  3. 每个风险点带 evidence_refs（引用文档 id），供 gate 校验与仲裁防幻觉；
  4. 故障隔离：LLM 调用失败 / 未生成风险点 → 降级直接检索后重试，再失败返回空结果。
"""
import asyncio
import json

from app.agent.prompts import load_prompt, load_risk_dim_prompt
from app.agent.state import ReviewState
from app.agent.tools.executor import call_llm_with_tools
from app.agent.tools.registry import default_tools
from app.core.config import get_settings
from app.rag.client import get_sf_client
from app.rag.service import RAGService

settings = get_settings()

MAX_REACT_ROUNDS = 3

TOOL_USAGE_HINT = (
    "\n\n【审阅工作流】\n"
    "1. 先使用 search_regulations 检索与条款相关的法规/制度/模板证据（可多轮、可换关键词）；\n"
    "2. 依据检索证据与条款原文输出风险点 JSON；\n"
    "3. 涉及金额计算时使用 calc_penalty 工具，禁止心算。"
)


def _normalize_level(level: str) -> str:
    """多供应商字段漂移归一化：high→高 / medium→中 / low→低。"""
    mapping = {"high": "高", "medium": "中", "low": "低", "严重": "高", "较高": "高", "一般": "中", "较低": "低"}
    return mapping.get(str(level).strip().lower(), level if level in {"高", "中", "低"} else "中")


def _parse_risk_points(raw: str) -> list[dict]:
    """解析专家输出 JSON；兼容 ```json 包裹与容错提取。

    归一化常见模型字段漂移：risk_type→risk_dim、risk_description/risk_details→risk_analysis、
    suggested_revision→suggested_content；risk_level 统一 高/中/低。
    """
    import re

    text = raw.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return []
    points = data.get("risk_points", [])
    if not isinstance(points, list):
        return []
    cleaned = []
    for p in points:
        if not isinstance(p, dict):
            continue
        original = (
            p.get("original_content")
            or p.get("original_text")
            or p.get("contract_clause")
            or p.get("clause_text")
            or ""
        )
        analysis = (
            p.get("risk_analysis")
            or p.get("risk_description")
            or p.get("risk_details")
            or p.get("analysis")
            or p.get("reason")
            or ""
        )
        suggestion = (
            p.get("suggested_content")
            or p.get("suggested_revision")
            or p.get("suggestion")
            or p.get("revision_suggestion")
            or ""
        )
        if not original and not analysis:
            continue
        cleaned.append(
            {
                "original_content": str(original)[:2000],
                "risk_analysis": str(analysis)[:2000],
                "risk_level": _normalize_level(str(p.get("risk_level", "中"))),
                "suggested_content": str(suggestion)[:2000],
                "evidence_refs": p.get("evidence_refs", []) if isinstance(p.get("evidence_refs"), list) else [],
                "risk_dim": str(p.get("risk_type") or p.get("risk_dim") or "")[:32],
            }
        )
    return cleaned


async def _run_specialist(
    sem: asyncio.Semaphore,
    chunk: str,
    risk_dim: str,
    state: ReviewState,
    rag: RAGService,
) -> dict:
    """单个 (chunk, risk_dim) 专家任务：真 ReAct 工具循环 + 故障隔离。"""
    async with sem:
        sf = get_sf_client()
        dim_prompt = load_risk_dim_prompt(risk_dim)
        system = load_prompt(
            "specialist_base",
            risk_dim=risk_dim,
            stance=state["stance"],
            intensity=state["intensity"],
        )
        if dim_prompt:
            system += f"\n\n【{risk_dim}审阅细则】\n{dim_prompt}"
        system += TOOL_USAGE_HINT

        contract_content = "\n".join(state["chunks"])

        ctx = {
            "rag": rag,
            "contract_content": contract_content,
            "clauses": state["chunks"],
        }

        user_msg = (
            f"【合同条款】\n{chunk}\n\n"
            f"请按审阅工作流检索证据后，输出该条款在【{risk_dim}】维度的审阅结果 JSON：\n"
            "{\"risk_points\": [{\"original_content\": \"条款原文摘录\", \"risk_analysis\": \"风险分析\", "
            "\"risk_level\": \"高|中|低\", \"suggested_content\": \"修改建议\", \"evidence_refs\": [\"引用的文档id\"]}]}\n"
            "若该条款在本维度无风险，输出 {\"risk_points\": []}。"
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]

        # 真 ReAct：模型自主调用工具（检索证据由模型生成 query）
        try:
            text, tool_log = await call_llm_with_tools(
                sf,
                messages,
                default_tools(),
                model=settings.llm_review_model,
                temperature=0.2,
                max_tokens=2048,
                context=ctx,
            )
            points = _parse_risk_points(text)
            # 条款原文兜底：模型未输出 original_content 时，用本条 chunk 作为条款上下文
            for p in points:
                if not p.get("original_content"):
                    p["original_content"] = chunk[:2000]
            if not points:
                # 未解析出风险点 → 检索证据后再试（降级路径）
                evidence_ctx, evidence = await rag.search_with_context(chunk, risk_dim=risk_dim, top_k=3)
                doc_ids = list({e.chunk.doc_id for e in evidence})
                messages.append({"role": "user", "content": f"【检索证据】\n{evidence_ctx}\n\n请据此重新输出审阅结果 JSON。"})
                try:
                    retry = await sf.chat(messages, model=settings.llm_review_model, temperature=0.2, max_tokens=2048)
                    points = _parse_risk_points(retry)
                    if points:
                        for p in points:
                            p.setdefault("evidence_refs", doc_ids)
                except Exception:  # noqa: BLE001
                    points = []
        except Exception as exc:  # noqa: BLE001 故障隔离：LLM 调用失败不拖垮整体
            state.setdefault("errors", []).append(f"specialist[{risk_dim}] llm error: {exc}")
            # 兜底：无模型结果，返回空（错误已记录）
            points = []

        # 证据引用回填：把本次工具调用检索到的 doc_id 合并进每个风险点
        if points:
            tool_doc_ids: list[str] = []
            for rec in tool_log:
                tool_doc_ids.extend(rec.doc_ids)
            tool_doc_ids = list(dict.fromkeys(tool_doc_ids))
            for p in points:
                refs = list(p.get("evidence_refs") or [])
                p["evidence_refs"] = list(dict.fromkeys(refs + tool_doc_ids))[:5]

            # 流式推送：单个专家任务完成即推 SSE（LangGraph custom stream mode）
            try:
                from langgraph.config import get_stream_writer

                get_stream_writer()(
                    {
                        "type": "risk_point",
                        "risk_dim": risk_dim,
                        "points": points,
                    }
                )
            except Exception:  # noqa: BLE001 writer 不可用时静默降级（非流式上下文）
                pass
            return {"chunk_index": state["chunks"].index(chunk), "risk_dim": risk_dim, "result": points}

        return {"chunk_index": state["chunks"].index(chunk), "risk_dim": risk_dim, "result": []}


async def specialist_node(state: ReviewState, rag: RAGService) -> dict:
    """map：并行执行所有 (chunk, risk_dim) 专家任务，信号量限流。"""
    sem = asyncio.Semaphore(state.get("max_concurrent", 20))
    tasks = [
        _run_specialist(sem, state["chunks"][r["chunk_index"]], dim, state, rag)
        for r in state["routed"]
        for dim in r["risk_dims"]
    ]
    outputs = await asyncio.gather(*tasks)
    return {"specialist_outputs": outputs}
