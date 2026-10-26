"""Review task orchestration: chunk -> LangGraph agent -> SSE streaming output."""
import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from anyio import CancelScope
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession

from app.agent.graph import get_graph
from app.agent.review_profiles import COMMON, get_profile, profile_scope, review_scope
from app.agent.state import ReviewState
from app.core.cache import acquire_lock, release_lock, renew_lock
from app.core.langfuse import traced
from app.core.metrics import record as record_metric
from app.core.runtime_config import prompt_scope
from app.core.storage import get_storage
from app.models.contract import ContractFile, ContractType
from app.models.review import ReviewResult, ReviewTask
from app.models.session_message import Session, SessionTypeEnum
from app.models.user import User
from app.rag.service import RAGService, get_rag_service
from app.schemas.review import ReviewStartRequest

CLAUSE_RE = re.compile(r"^第[一二三四五六七八九十百千0-9]+[条款]")


def resolve_review_type(db, contract, requested=""):
    assigned = db.get(ContractType, contract.contract_type_id) if contract.contract_type_id else None
    requested = requested.strip()
    if assigned is not None:
        if not assigned.is_active:
            raise HTTPException(422, "合同类型已停用，请先选择启用的合同类型")
        same_profile = get_profile(requested) is not COMMON and get_profile(requested) is get_profile(assigned.name)
        if requested and requested != assigned.name and not same_profile:
            raise HTTPException(422, "审阅类型与合同保存的类型不一致，请刷新后重新选择")
        return assigned.name, assigned.id
    selected = db.query(ContractType).filter_by(name=requested).first() if requested else None
    if selected is None and requested and get_profile(requested) is not COMMON:
        selected = db.query(ContractType).filter_by(name=get_profile(requested).name).first()
    if selected is not None and not selected.is_active:
        raise HTTPException(422, "合同类型已停用，请先选择启用的合同类型")
    return (selected.name, selected.id) if selected else (requested, None)


def split_contract_clauses(text: str, max_chars: int = 1500) -> list[str]:
    """按 '第X条' 切分；无条款结构时按长度切分。"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    clauses: list[str] = []
    buf: list[str] = []
    for line in lines:
        if CLAUSE_RE.match(line):
            if buf:
                clauses.append("\n".join(buf))
            buf = [line]
        else:
            buf.append(line)
    if buf:
        clauses.append("\n".join(buf))

    # 超长块再切
    out: list[str] = []
    for c in clauses:
        if len(c) <= max_chars:
            out.append(c)
        else:
            for i in range(0, len(c), max_chars):
                out.append(c[i : i + max_chars])
    return out or [text[:max_chars]]


def _supplement_contracts(db, user_id: int, primary_file_id: int, file_ids: list[int]):
    unique_ids = list(dict.fromkeys(file_ids))
    if primary_file_id in unique_ids:
        raise HTTPException(422, "主合同不能同时作为补充材料")
    if not unique_ids:
        return []
    records = db.query(ContractFile).filter(
        ContractFile.id.in_(unique_ids), ContractFile.user_id == user_id,
    ).all()
    by_id = {record.id: record for record in records}
    if any(file_id not in by_id for file_id in unique_ids):
        raise HTTPException(404, "Supplement file not found")
    ordered = [by_id[file_id] for file_id in unique_ids]
    if any(record.parse_status != "parsed" or not record.content_path for record in ordered):
        raise HTTPException(400, "补充材料尚未解析完成，暂不能用于审阅")
    return ordered


async def stream_review_events(
    request: ReviewStartRequest,
    current_user: User,
    db: DBSession,
    rag: RAGService | None = None,
    *,
    lock_token: str | None = None,
    on_complete: Callable | None = None,
    commit_guard: Callable[[], Awaitable[bool]] | None = None,
) -> StreamingResponse:
    session = db.get(Session, request.session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(404, "Session not found")
    if session.session_type != SessionTypeEnum.REVIEW:
        raise HTTPException(400, "A review session is required")
    contract = db.get(ContractFile, session.file_id) if session.file_id else None
    if contract is None or contract.user_id != current_user.id:
        raise HTTPException(404, "Contract file not found")
    if contract.parse_status != "parsed" or not contract.content_path:
        raise HTTPException(400, "File not parsed, review unsupported")
    contract_type, contract_type_id = resolve_review_type(db, contract, request.contract_type)

    storage = get_storage()
    content = storage.read_text(contract.content_path)
    primary_chunks = split_contract_clauses(content)
    supplements = _supplement_contracts(
        db, current_user.id, contract.id, request.supplement_file_ids,
    )
    chunks = list(primary_chunks)
    supplement_files = [{"file_id": item.id, "title": item.title} for item in supplements]
    for item in supplements:
        supplemental_text = storage.read_text(item.content_path)
        chunks.extend(
            f"【补充材料：{item.title}】\n{chunk}"
            for chunk in split_contract_clauses(supplemental_text)
        )
    scope = review_scope(contract_type)
    scope["supplement_files"] = supplement_files

    state: ReviewState = {
        "session_id": request.session_id,
        "file_id": contract.id,
        "user_id": current_user.id,
        "contract_type": contract_type,
        "review_scope": scope,
        "supplement_files": supplement_files,
        "stance": request.stance,
        "intensity": request.intensity,
        "description": request.description or "",
        "max_concurrent": request.max_concurrent,
        "content_path": contract.content_path or "",
        "chunks": chunks,
        "intent": "review",
        "intent_confidence": 1.0,
        "routed": [],
        "specialist_outputs": [],
        "gated": [],
        "final_risk_points": [],
        "summary": {},
        "errors": [],
    }

    async def gen():
        # Redis 并发锁：同一会话只允许一个审阅任务（防止并发互删旧结果）
        lock_key = f"review_lock:{request.session_id}"
        owner_token = lock_token or f"{request.session_id}-{id(request)}"
        if not await acquire_lock(lock_key, owner_token, ttl=900):
            yield f"data: {json.dumps({'event': 'error', 'data': {'message': '该会话已有审阅任务进行中，请等待完成'}}, ensure_ascii=False)}\n\n"
            return
        t0 = time.monotonic()
        task = None
        stream = None
        try:
            # Retain the last successful result until the replacement commits in full.
            task = ReviewTask(
                session_id=request.session_id, file_id=state["file_id"],
                user_id=state["user_id"], stance=request.stance, intensity=request.intensity,
                description=request.description or "", contract_type=contract_type,
                status="processing",
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            task_id = task.id
            # End the refresh-only transaction before waiting on model inference.
            # Background reviews must not occupy a DB connection for their full duration.
            db.rollback()
            # 首事件 meta 骨架：与 LLM 无关，首字节 <100ms 必达
            # （routed/risk_dims 此时尚未由 router 节点填充，故不输出，避免误导）
            yield f"data: {json.dumps({'event': 'meta', 'data': {'task_id': task_id, 'session_id': request.session_id, 'chunk_count': len(chunks), 'review_scope': scope}}, ensure_ascii=False)}\n\n"
            graph = get_graph(rag or get_rag_service())
            # 流式执行：custom 模式推送专家实时结果，updates 模式收集仲裁后的最终状态
            stream = graph.astream(state, stream_mode=["custom", "updates"])
            final_points: list[dict] = []
            summary: dict = {}
            arbitration_seen = False
            streamed_index = 0
            async for mode, payload in stream:
                if mode == "custom":
                    if isinstance(payload, dict) and payload.get("type") == "risk_point":
                        for p in payload.get("points", []):
                            if isinstance(p, dict):
                                streamed_index += 1
                                streamed_point = {
                                    **p,
                                    "index": p.get("index") or streamed_index,
                                    "risk_dim": p.get("risk_dim") or payload.get("risk_dim", ""),
                                }
                                yield f"data: {json.dumps({'event': 'message', 'data': streamed_point}, ensure_ascii=False)}\n\n"
                                await asyncio.sleep(0.01)
                elif mode == "updates":
                    for node, upd in payload.items():
                        if node == "arbitration" and isinstance(upd, dict):
                            arbitration_seen = True
                            final_points = upd.get("final_risk_points") or []
                            summary = upd.get("summary") or {}

            points = final_points

            if not arbitration_seen:
                raise RuntimeError("审阅未生成最终结论，已有结果已保留")
            if not await renew_lock(lock_key, owner_token, ttl=900):
                raise RuntimeError("审阅锁已过期，本次结果未替换已有结果，请重试")
            if commit_guard is not None and not await commit_guard():
                raise RuntimeError("后台任务失去执行权，本次结果未替换已有结果，请重新发起")
            from app.services.review_history import archive_replaced_reviews

            archive_replaced_reviews(db, request.session_id, task.id, state["user_id"])
            # Replace results atomically. A failed or disconnected run keeps prior results.
            records = []
            for idx, point in enumerate(points, start=1):
                record = ReviewResult(
                    task_id=task.id, session_id=request.session_id, index=idx,
                    original_content=point.get("original_content", ""),
                    risk_analysis=point.get("risk_analysis", ""),
                    risk_level=point.get("risk_level", "中"),
                    suggested_content=point.get("suggested_content", ""),
                    risk_dim=point.get("risk_dim", ""),
                )
                db.add(record)
                records.append(record)
            old_ids = db.query(ReviewTask.id).filter(
                ReviewTask.session_id == request.session_id, ReviewTask.id != task.id,
                ReviewTask.status != "processing",
            ).scalar_subquery()
            db.query(ReviewResult).filter(ReviewResult.task_id.in_(old_ids)).delete(
                synchronize_session=False,
            )
            db.query(ReviewTask).filter(
                ReviewTask.session_id == request.session_id, ReviewTask.id != task.id,
                ReviewTask.status != "processing",
            ).delete(synchronize_session=False)
            task.status = "completed"
            task.completed_at = datetime.now(UTC)
            duration_ms = (time.monotonic() - t0) * 1000
            end_data = {
                "type": "summary", "summary": summary.get("summary", ""),
                "suggestion": summary.get("suggestion", ""),
                "overall_risk": summary.get("overall_risk", "低"),
                "review_status": summary.get("review_status", "incomplete"),
                "review_scope": summary.get("review_scope") or scope,
                "metrics": {"total_ms": round(duration_ms, 1), "risk_point_count": len(points)},
            }
            if on_complete is not None:
                db.flush()
                on_complete(task, records, end_data)
            db.commit()
            for record in records:
                msg = {"event": "message", "data": {
                    "id": record.id, "task_id": task.id, "session_id": request.session_id,
                    "index": record.index, "original_content": record.original_content,
                    "risk_analysis": record.risk_analysis, "risk_level": record.risk_level,
                    "suggested_content": record.suggested_content, "risk_dim": record.risk_dim,
                }}
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"

            record_metric("review", ttft_ms=None, total_ms=duration_ms, tokens=None)

            end_msg = json.dumps(
                {
                    "event": "end",
                    "data": end_data,
                },
                ensure_ascii=False,
            )
            yield f"data: {end_msg}\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            db.rollback()
            if task is not None and task.status == "processing":
                task.status = "cancelled"
                db.commit()
            raise
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            if task is not None and task.status == "processing":
                task.status = "failed"
                db.commit()
            yield f"data: {json.dumps({'event': 'error', 'data': {'message': str(exc)}}, ensure_ascii=False)}\n\n"
        finally:
            with CancelScope(shield=True):
                try:
                    if stream is not None:
                        await stream.aclose()
                finally:
                    await release_lock(lock_key, owner_token)

    @traced("review", session_id=request.session_id)
    async def scoped_gen():
        from contextlib import aclosing

        with prompt_scope(contract_type_id), profile_scope(contract_type):
            async with aclosing(gen()) as source:
                async for frame in source:
                    yield frame

    return StreamingResponse(scoped_gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })
