"""Create review-aware chats and render bounded review context for each question."""
import json
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.models.review_chat import ReviewChatContext
from app.models.session_message import Session, SessionTypeEnum
from app.services.review_history import history_detail

settings = get_settings()


def _snapshot(data: dict) -> dict:
    summary = data.get("summary") or {}
    return {
        "review_id": data["id"],
        "contract_title": data.get("title", ""),
        "file_id": data.get("file_id"),
        "contract_type": data.get("contract_type", ""),
        "stance": data.get("stance", ""),
        "intensity": data.get("intensity", ""),
        "description": data.get("description", ""),
        "review_status": summary.get("review_status"),
        "overall_risk": summary.get("overall_risk"),
        "summary": summary.get("summary", ""),
        "suggestion": summary.get("suggestion", ""),
        "review_scope": summary.get("review_scope") or data.get("review_scope") or {},
        "risk_points": data.get("risk_points", []),
        "material_decision": data.get("material_decision"),
        "chosen_supplement_file_ids": data.get("chosen_supplement_file_ids", []),
        "created_at": data.get("created_at"),
        "completed_at": data.get("completed_at"),
    }


async def get_or_create_review_chat(
    db: DBSession, user_id: int, history_id: str,
) -> tuple[Session, ReviewChatContext]:
    data = await history_detail(db, user_id, history_id)
    if data["status"] != "completed":
        raise HTTPException(409, "审阅完成后才能基于结果发起答疑")

    context = db.query(ReviewChatContext).filter_by(
        user_id=user_id, source_review_id=history_id,
    ).order_by(ReviewChatContext.created_at.desc()).first()
    if context is not None:
        session = db.get(Session, context.session_id)
        if session is not None and session.user_id == user_id:
            context.snapshot = _snapshot(data)
            db.commit()
            db.refresh(session)
            return session, context

    title = f"审阅答疑 · {data.get('title') or '合同'}"[:255]
    session = Session(
        user_id=user_id, title=title, session_type=SessionTypeEnum.CHAT,
        file_id=data.get("file_id"),
    )
    db.add(session)
    db.flush()
    context = ReviewChatContext(
        session_id=session.id, user_id=user_id,
        source_review_id=history_id, snapshot=_snapshot(data),
    )
    db.add(context)
    db.commit()
    db.refresh(session)
    return session, context


def _terms(text: str) -> set[str]:
    terms = set(re.findall(r"[a-zA-Z0-9]+", text.lower()))
    for segment in re.findall(r"[\u4e00-\u9fff]+", text):
        terms.update(segment[index:index + 2] for index in range(len(segment) - 1))
    return terms


def _point_text(point: dict) -> str:
    return " ".join(str(point.get(key, "")) for key in (
        "index", "risk_dim", "risk_level", "original_content", "risk_analysis", "suggested_content",
    ))


def render_review_context(snapshot: dict, query: str) -> str:
    """Keep the full snapshot in storage, while bounding each model request."""
    points = [point for point in snapshot.get("risk_points", []) if isinstance(point, dict)]
    metadata = {key: value for key, value in snapshot.items() if key != "risk_points"}
    payload = {**metadata, "risk_point_count": len(points), "risk_points": points}
    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    budget = settings.chat_review_context_max_chars
    if len(serialized) <= budget:
        return serialized

    requested = {int(value) for value in re.findall(r"第\s*(\d+)\s*(?:条|项|点)?", query)}
    query_terms = _terms(query)
    ranked = sorted(points, key=lambda point: (
        int(point.get("index") in requested) * 1000
        + len(query_terms & _terms(_point_text(point))),
        -int(point.get("index") or 0),
    ), reverse=True)
    selected = []
    for point in ranked:
        candidate = {**metadata, "risk_point_count": len(points), "risk_points": [*selected, point],
                     "context_note": "审阅结果过长，本轮按问题加载最相关风险点；完整结果仍保存在会话关联记录中。"}
        if len(json.dumps(candidate, ensure_ascii=False, default=str)) > budget:
            break
        selected.append(point)
    return json.dumps({
        **metadata,
        "risk_point_count": len(points),
        "included_risk_point_count": len(selected),
        "context_note": "审阅结果过长，本轮按问题加载最相关风险点；可指明风险点序号继续追问。",
        "risk_points": selected,
    }, ensure_ascii=False, default=str)
