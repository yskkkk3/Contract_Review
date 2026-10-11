"""Chat routes: SSE streaming chat around a contract session."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db
from app.core.security import get_current_user
from app.models.session_message import Session
from app.models.user import User
from app.schemas.chat import ChatRequest

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("")
async def chat(
    request: ChatRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """流式聊天（SSE）。实现见 app/services/chat_service.py（M4）。"""
    if request.session_id is None:
        raise HTTPException(400, "session_id required")
    session = db.get(Session, request.session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(404, "Session not found")
    from app.services.chat_service import stream_chat

    return await stream_chat(request, session, current_user, db)
