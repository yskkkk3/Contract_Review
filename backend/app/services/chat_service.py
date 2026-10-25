"""Chat streaming service: SSE response with context from contract + history.

简历点：首 Token 工程——流式事件通道（start/delta/usage）计时 TTFT，
done 事件携带 ttft_ms / tokens / TPOT，指标进 /api/metrics 滑动窗口。
"""
import asyncio
import json
import logging
import time
from contextlib import suppress

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession

from app.agent.prompts import load_prompt
from app.core.config import get_settings
from app.core.metrics import record
from app.models.session_message import Message, Session
from app.models.user import User
from app.rag.client import get_sf_client
from app.schemas.chat import ChatRequest
from app.services.chat_history import select_history
from app.services.contract_context import contract_text_cache

settings = get_settings()

SYSTEM_TEMPLATE = load_prompt("chat")
logger = logging.getLogger(__name__)


class ChatStreamTimeout(TimeoutError):
    pass


async def _stream_events(client, messages: list[dict]):
    """Keep the browser alive while enforcing upstream idle and first-answer deadlines."""
    source = client.chat_stream_events(messages, model=settings.llm_chat_model)
    loop = asyncio.get_running_loop()
    first_deadline = loop.time() + settings.chat_first_content_timeout
    idle_deadline = loop.time() + settings.chat_stream_timeout
    first_content = False
    pending = None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(source))
                idle_deadline = loop.time() + settings.chat_stream_timeout
            now = loop.time()
            deadline = idle_deadline if first_content else min(idle_deadline, first_deadline)
            if now >= deadline:
                message = ("等待回答超时，请稍后重试" if not first_content
                           else "回答传输超时，当前内容尚未完成，请重试")
                raise ChatStreamTimeout(message)
            done, _ = await asyncio.wait(
                {pending}, timeout=min(settings.chat_heartbeat_interval, deadline - now),
            )
            if not done:
                yield "heartbeat", None
                continue
            try:
                kind, payload = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            if kind == "delta" and payload:
                first_content = True
            yield kind, payload
    finally:
        if pending is not None:
            pending.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await pending
        await source.aclose()


async def _history_messages(db: DBSession, session_id: int) -> list[dict]:
    """返回当前会话的完整消息历史，供模型保持会话内记忆。"""
    def load():
        rows = (db.query(Message.role, Message.content)
                .filter(Message.session_id == session_id)
                .order_by(Message.id.asc()).all())
        return [{"role": m.role, "content": m.content} for m in rows]

    return await asyncio.to_thread(load)


def _load_contract_text(db: DBSession, session: Session) -> str:
    from app.models.contract import ContractFile

    if not session.file_id:
        return ""
    contract = db.get(ContractFile, session.file_id)
    if contract is None or contract.user_id != session.user_id:
        from fastapi import HTTPException

        raise HTTPException(404, "Contract file not found")
    if not contract.content_path:
        return ""
    try:
        return contract_text_cache.read(contract.user_id, contract.id, contract.content_path)
    except (OSError, RuntimeError):
        return ""


async def stream_chat(
    request: ChatRequest, session: Session, current_user: User, db: DBSession,
    *, started_at: float | None = None,
) -> StreamingResponse:
    started_at = started_at if started_at is not None else time.monotonic()
    # ORM objects expire on commit; do not reopen a DB transaction while streaming.
    session_id = session.id
    phases: dict[str, float] = {}

    def elapsed(start: float) -> float:
        return (time.monotonic() - start) * 1000

    try:
        client = get_sf_client()
        phase_start = time.monotonic()
        contract_text = await asyncio.to_thread(_load_contract_text, db, session)
        phases["contract_load_ms"] = elapsed(phase_start)
        phase_start = time.monotonic()
        history = await _history_messages(db, session_id)
        phases["history_load_ms"] = elapsed(phase_start)
        phase_start = time.monotonic()
        history_chars = sum(len(m["content"]) for m in history)
        history = select_history(history, request.content or "")
        context_chars = sum(len(m["content"]) for m in history)
        phases["history_select_ms"] = elapsed(phase_start)
        phase_start = time.monotonic()
        db.add(Message(
            session_id=session_id, role="user", content=request.content or "",
            parent_id=request.parent_id,
        ))
        db.commit()
        phases["user_persist_ms"] = elapsed(phase_start)
        phases["preparation_ms"] = elapsed(started_at)
    except BaseException as exc:
        record("chat", total_ms=elapsed(started_at), phases_ms=phases,
               status="cancelled" if isinstance(exc, asyncio.CancelledError) else "error")
        raise

    system = SYSTEM_TEMPLATE
    if contract_text:
        system += f"\n\n合同原文（节选）：\n{contract_text}"

    full_content: list[str] = []
    usage: dict = {}

    async def gen():
        model_started = time.monotonic()
        ttft_ms: float | None = None
        status = "success"
        model_events = _stream_events(client, [
            {"role": "system", "content": system}, *history,
            {"role": "user", "content": request.content or ""},
        ])
        try:
            yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"
            async for kind, payload in model_events:
                if kind == "delta":
                    if ttft_ms is None:
                        ttft_ms = elapsed(started_at)
                        phases["model_first_content_ms"] = elapsed(model_started)
                    full_content.append(payload)
                    yield f"data: {json.dumps({'type': 'content', 'content': payload, 'session_id': session_id}, ensure_ascii=False)}\n\n"
                elif kind == "usage":
                    usage.update(payload)
                    yield f"data: {json.dumps({'type': 'usage', 'usage': payload})}\n\n"
                elif kind == "start":
                    yield 'data: {"type": "status", "phase": "analyzing"}\n\n'
                elif kind == "heartbeat":
                    yield ": heartbeat\n\n"
            phases["model_total_ms"] = elapsed(model_started)
            if ttft_ms is not None:
                phases["generation_ms"] = phases["model_total_ms"] - phases["model_first_content_ms"]
            text = "".join(full_content)
            if not text.strip():
                raise ValueError("upstream returned no answer content")
            phase_start = time.monotonic()
            message = Message(session_id=session_id, role="assistant", content=text)
            db.add(message)
            db.commit()
            db.refresh(message)
            phases["assistant_persist_ms"] = elapsed(phase_start)
            total_ms = elapsed(started_at)
            completion_tokens = usage.get("completion_tokens")
            metrics = {
                "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
                "total_ms": round(total_ms, 1),
                "completion_tokens": completion_tokens,
                "tokens_per_sec": round((completion_tokens or 0) / (total_ms / 1000), 1)
                if total_ms > 0 else 0,
                "phases_ms": {key: round(value, 1) for key, value in phases.items()},
                "history_chars": history_chars,
                "history_context_chars": context_chars,
            }
            yield f"data: {json.dumps({'type': 'done', 'message_id': message.id, 'full_content': text, 'metrics': metrics}, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except GeneratorExit:
            status = "cancelled"
            raise
        except ChatStreamTimeout as exc:
            status = "timeout"
            yield f"data: {json.dumps({'type': 'error', 'code': 'timeout', 'message': str(exc), 'partial': bool(full_content)}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            status = "error"
            db.rollback()
            logger.warning("Chat stream failed session_id=%s error_type=%s", session_id, type(exc).__name__)
            message = "回答生成失败，当前内容尚未完成，请重试" if full_content else "回答生成失败，请稍后重试"
            yield f"data: {json.dumps({'type': 'error', 'code': 'chat_error', 'message': message, 'partial': bool(full_content)}, ensure_ascii=False)}\n\n"
        finally:
            try:
                await model_events.aclose()
            finally:
                phases.setdefault("model_total_ms", elapsed(model_started))
                record("chat", ttft_ms=ttft_ms, total_ms=elapsed(started_at),
                       tokens=usage.get("completion_tokens"), phases_ms=phases, status=status)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })
