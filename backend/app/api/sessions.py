"""Session routes: create / list / rename / delete / history."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db
from app.core.security import get_current_user
from app.models import Message, ReviewResult, Session, SessionTypeEnum
from app.models.comparison import ComparisonTask
from app.models.contract import ContractFile
from app.models.review import ReviewTask
from app.models.user import User
from app.schemas.base import GenericResponse, PageResponse
from app.schemas.comparison import ComparisonResponse, DiffSummary, FileInfo, ParagraphDiff
from app.schemas.session import (
    CreateSessionRequest,
    SessionResponse,
    UpdateSessionTitleRequest,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=GenericResponse[SessionResponse])
async def create_session(
    request: CreateSessionRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if request.file_id:
        contract = db.get(ContractFile, request.file_id)
        if contract is None:
            raise HTTPException(404, "Contract file not found")
    session = Session(
        user_id=current_user.id,
        title=request.title,
        session_type=SessionTypeEnum(request.session_type),
        file_id=request.file_id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return GenericResponse(data=_to_response(session))


@router.get("", response_model=GenericResponse[PageResponse[SessionResponse]])
async def list_sessions(
    session_type: str,
    page: int = 1,
    page_size: int = 20,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Session).filter(
        Session.user_id == current_user.id,
        Session.session_type == SessionTypeEnum(session_type),
    )
    total = q.count()
    sessions = (
        q.order_by(Session.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return GenericResponse(
        data=PageResponse(items=[_to_response(s) for s in sessions], total=total, page=page, page_size=page_size)
    )


@router.put("/{session_id}/title", response_model=GenericResponse[SessionResponse])
async def update_title(
    session_id: int, request: UpdateSessionTitleRequest,
    db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    session = db.get(Session, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(404, "Session not found")
    session.title = request.new_title
    db.commit()
    db.refresh(session)
    return GenericResponse(data=_to_response(session))


@router.delete("/{session_id}", response_model=GenericResponse)
async def delete_session(
    session_id: int, db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.get(Session, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(404, "Session not found")
    db.delete(session)
    db.commit()
    return GenericResponse(msg="session deleted")


@router.get("/{session_id}/history", response_model=GenericResponse)
async def session_history(
    session_id: int, db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.get(Session, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(404, "Session not found")

    if session.session_type == SessionTypeEnum.CHAT:
        messages = (
            db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.created_at)
            .all()
        )
        return GenericResponse(data=[_msg_dict(m) for m in messages])

    if session.session_type == SessionTypeEnum.REVIEW:
        task = db.query(ReviewTask).filter(ReviewTask.session_id == session_id).first()
        if task is None:
            return GenericResponse(data=[])
        results = (
            db.query(ReviewResult)
            .filter(ReviewResult.task_id == task.id)
            .order_by(ReviewResult.index)
            .all()
        )
        return GenericResponse(
            data={"task_id": task.id, "status": task.status, "risk_points": [_risk_dict(r) for r in results]}
        )

    if session.session_type == SessionTypeEnum.COMPARE:
        task = db.query(ComparisonTask).filter(ComparisonTask.session_id == session_id).first()
        if task is None:
            raise HTTPException(404, "Comparison record not found")
        std = db.get(ContractFile, task.standard_file_id)
        cmp = db.get(ContractFile, task.comparison_file_id)
        import json

        return GenericResponse(
            data=ComparisonResponse(
                task_id=task.id,
                session_id=session_id,
                diff_summary=DiffSummary(**json.loads(task.diff_summary or "{}")),
                diffs=[ParagraphDiff(**d) for d in json.loads(task.diff_result or "[]")],
                standard_file=FileInfo(
                    file_id=std.id, title=std.title, file_type=std.file_type,
                    download_url=f"/api/contracts/{std.id}/download",
                ) if std else FileInfo(file_id=0, title="", file_type="", download_url=""),
                comparison_file=FileInfo(
                    file_id=cmp.id, title=cmp.title, file_type=cmp.file_type,
                    download_url=f"/api/contracts/{cmp.id}/download",
                ) if cmp else FileInfo(file_id=0, title="", file_type="", download_url=""),
            )
        )
    raise HTTPException(400, "Unsupported session type")


def _to_response(s: Session) -> SessionResponse:
    return SessionResponse(
        session_id=s.id, title=s.title, session_type=s.session_type.value,
        file_id=s.file_id, created_at=s.created_at,
    )


def _msg_dict(m: Message) -> dict:
    return {
        "id": m.id, "session_id": m.session_id, "role": m.role, "content": m.content,
        "parent_id": m.parent_id, "message_index": m.message_index, "created_at": str(m.created_at),
    }


def _risk_dict(r: ReviewResult) -> dict:
    return {
        "id": r.id, "task_id": r.task_id, "session_id": r.session_id, "index": r.index,
        "original_content": r.original_content, "risk_analysis": r.risk_analysis,
        "risk_level": r.risk_level, "suggested_content": r.suggested_content,
        "risk_dim": r.risk_dim, "is_accepted": r.is_accepted,
    }
