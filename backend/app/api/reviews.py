"""Review routes: SSE streaming review + accept risk points."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db
from app.core.security import get_current_user
from app.models.contract import ContractFile
from app.models.review import ReviewResult
from app.models.user import User
from app.schemas.base import GenericResponse
from app.schemas.review import AcceptContractFileRequest, AcceptRiskPointRequest, ReviewStartRequest

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("/start")
async def start_review(
    request: ReviewStartRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """启动审阅任务（SSE）。实现见 app/services/review_service.py（M3 Agent 编排）。"""
    from app.services.review_service import stream_review_events

    return await stream_review_events(request, current_user, db)


@router.post("/risk-points/accept", response_model=GenericResponse)
async def accept_risk_point(
    request: AcceptRiskPointRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = (
        db.query(ReviewResult)
        .filter(
            ReviewResult.task_id == request.task_id,
            ReviewResult.session_id == request.session_id,
            ReviewResult.index == request.index,
        )
        .first()
    )
    if result is None:
        raise HTTPException(404, "Risk point not found")
    result.is_accepted = request.is_accepted
    db.commit()
    return GenericResponse(msg="ok", data=True)


@router.post("/contracts/accept", response_model=GenericResponse)
async def accept_contract_file(
    request: AcceptContractFileRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.get(ContractFile, request.file_id)
    if record is None:
        raise HTTPException(404, "Contract file not found")
    record.is_accepted = request.is_accepted
    db.commit()
    return GenericResponse(msg="ok", data=True)
