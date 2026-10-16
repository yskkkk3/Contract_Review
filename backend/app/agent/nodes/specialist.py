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
from app.rag.client import _extract_json, get_sf_client, is_provider_access_error
from app.rag.service import RAGService

settings = get_settings()

MAX_REACT_ROUNDS = 3

AUDIT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["complete", "revised", "incomplete"]},
        "unresolved": {"type": "array", "items": {"type": "string"}},
        "risk_points": {
            "type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "original_content": {"type": "string"}, "risk_analysis": {"type": "string"},
                    "risk_level": {"type": "string", "enum": ["高", "中", "低"]},
                    "suggested_content": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["original_content", "risk_analysis", "risk_level", "suggested_content", "evidence_refs"],
            },
        },
    },
    "required": ["status", "unresolved", "risk_points"],
}

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
        system += "\n\n" + load_prompt("legal_evidence")

        contract_content = "\n".join(state["chunks"])

        ctx = {
            "rag": rag,
            "contract_content": contract_content,
            "clauses": state["chunks"],
            "evidence_seen": [],
        }
        supplement = rag.legal_supplement(chunk, risk_dim) if isinstance(rag, RAGService) else None
        if supplement:
            ctx["evidence_seen"].extend(supplement.evidence)
        diagnostics: list[str] = []
        provider_unavailable = False

        user_msg = (
            f"【合同条款】\n{chunk}\n\n"
            f"请按审阅工作流检索证据后，输出该条款在【{risk_dim}】维度的审阅结果 JSON：\n"
            "{\"risk_points\": [{\"original_content\": \"条款原文摘录\", \"risk_analysis\": \"风险分析\", "
            "\"risk_level\": \"高|中|低\", \"suggested_content\": \"修改建议\", \"evidence_refs\": [\"引用的文档id\"]}]}\n"
            "若该条款在本维度无风险，输出 {\"risk_points\": []}。"
        )
        background = [
            {"clause_index": index, "text": clause[:600]}
            for index, clause in enumerate(state["chunks"])
            if any(word in clause for word in ("甲方", "乙方", "财政", "资金", "签订日期", "事业单位", "中小企业"))
        ][:4]
        user_msg += "\n【合同背景摘录，其他条款可按索引补查】\n" + json.dumps(background, ensure_ascii=False)
        if supplement and supplement.text:
            user_msg += "\n【关键规则及关联条件补查】\n" + supplement.text

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]

        # 仅保留模型实际引用且本轮真实检索到的文档，不把全部命中回填为依据。
        retrieved_doc_ids: set[str] = {item.chunk.doc_id for item in ctx["evidence_seen"]}
        try:
            text, tool_log = await call_llm_with_tools(
                sf,
                messages,
                default_tools(),
                model=settings.llm_review_model,
                temperature=0.2,
                max_tokens=settings.agent_review_max_tokens,
                context=ctx,
            )
            retrieved_doc_ids.update(doc_id for rec in tool_log if rec.ok for doc_id in rec.doc_ids)
            points = _parse_risk_points(text)
            # 条款原文兜底：模型未输出 original_content 时，用本条 chunk 作为条款上下文
            for p in points:
                if not p.get("original_content"):
                    p["original_content"] = chunk[:2000]
            if not points and (_extract_json(text) or {}).get("risk_points") != []:
                # 未解析出风险点 → 检索证据后再试（降级路径）
                evidence_ctx, evidence = await rag.search_with_context(chunk, risk_dim=risk_dim, top_k=3)
                retrieved_doc_ids.update(e.chunk.doc_id for e in evidence)
                ctx["evidence_seen"].extend(evidence)
                messages.append({"role": "user", "content": f"【检索证据】\n{evidence_ctx}\n\n请据此重新输出审阅结果 JSON。"})
                try:
                    retry = await sf.chat(messages, model=settings.llm_review_model, temperature=0.2,
                                          max_tokens=settings.agent_review_max_tokens, brief=True)
                    points = _parse_risk_points(retry)
                    if not points and (_extract_json(retry) or {}).get("risk_points") != []:
                        diagnostics.append("专家未返回有效审阅JSON，不能作为无风险结论")
                except Exception:  # noqa: BLE001
                    points = []
                    diagnostics.append("专家降级重试失败，审阅未完成")
        except Exception as exc:  # noqa: BLE001 故障隔离：LLM 调用失败不拖垮整体
            provider_unavailable = is_provider_access_error(exc)
            status = f" HTTP{exc.status_code}" if provider_unavailable else ""
            diagnostics.append(f"specialist[{risk_dim}] failed: {type(exc).__name__}{status}")
            # 兜底：无模型结果，返回空（错误已记录）
            points = []

        initial_points = [dict(point) for point in points]
        audit_status = "not_run"
        if isinstance(rag, RAGService):
            supplement = rag.legal_supplement(chunk, risk_dim, ctx["evidence_seen"])
        if (supplement and supplement.coverage.facets and settings.agent_evidence_audit_enabled
                and not provider_unavailable):
            try:
                audit = await asyncio.wait_for(sf.chat_structured(
                    [
                        {"role": "system", "content": load_prompt("review_completeness")},
                        {"role": "user", "content": json.dumps({
                            "clause": chunk, "risk_dim": risk_dim, "background": background,
                            "evidence_context": supplement.text, "draft": points,
                        }, ensure_ascii=False)},
                    ],
                    json_schema=AUDIT_SCHEMA, model=settings.llm_review_model,
                    temperature=0, max_tokens=settings.agent_review_max_tokens,
                ), timeout=settings.agent_evidence_audit_timeout)
                if (isinstance(audit, dict) and audit.get("status") in {"complete", "revised", "incomplete"}
                        and isinstance(audit.get("risk_points"), list)
                        and isinstance(audit.get("unresolved"), list)
                        and all(isinstance(item, str) for item in audit["unresolved"])):
                    audited_points = _parse_risk_points(json.dumps(audit, ensure_ascii=False))
                    if len(audited_points) != len(audit["risk_points"]):
                        raise ValueError("Invalid audited risk points")
                    points = audited_points
                    audit_status = audit["status"]
                    if audit["status"] == "incomplete" or audit["unresolved"]:
                        diagnostics.append("完整性复核仍有关键依据或材料待核实")
                else:
                    audit_status = "invalid"
                    diagnostics.append("完整性复核未返回有效结果")
            except Exception as exc:  # noqa: BLE001 审阅意见保留，但不能声称完整性已验证
                audit_status = "failed"
                diagnostics.append(f"完整性复核未完成：{type(exc).__name__}")
        if points:
            for p in points:
                refs = [
                    ref for ref in p.get("evidence_refs", [])
                    if isinstance(ref, str) and ref in retrieved_doc_ids
                ]
                p["evidence_refs"] = list(dict.fromkeys(refs))[:5]

        return {
            "chunk_index": state["chunks"].index(chunk), "risk_dim": risk_dim, "result": points,
            "evidence_context": supplement.text if supplement else "",
            "coverage_issues": supplement.coverage.missing if supplement else [],
            "diagnostics": diagnostics,
            "initial_result": initial_points, "audit_status": audit_status,
        }


async def specialist_node(state: ReviewState, rag: RAGService) -> dict:
    """map：并行执行所有 (chunk, risk_dim) 专家任务，信号量限流。"""
    sem = asyncio.Semaphore(state.get("max_concurrent", 20))
    tasks = [
        _run_specialist(sem, state["chunks"][r["chunk_index"]], dim, state, rag)
        for r in state["routed"]
        for dim in r["risk_dims"]
    ]
    outputs = await asyncio.gather(*tasks)
    errors = list(state.get("errors", []))
    for output in outputs:
        errors.extend(output.get("diagnostics", []))
        if output.get("coverage_issues"):
            errors.append(f"{output['risk_dim']}关键依据未完整覆盖：{', '.join(output['coverage_issues'])}")
    return {"specialist_outputs": outputs, "errors": errors}
