"""Review routes: background jobs, history, SSE compatibility and risk acceptance."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db
from app.core.runtime_config import runtime_dependency
from app.core.security import get_current_user
from app.models.contract import ContractFile
from app.models.review import ReviewJob, ReviewResult, ReviewTask
from app.models.user import User
from app.schemas.base import GenericResponse
from app.schemas.review import AcceptContractFileRequest, AcceptRiskPointRequest, ReviewStartRequest

router = APIRouter(prefix="/reviews", tags=["reviews"], dependencies=[Depends(runtime_dependency)])


@router.get("/history", response_model=GenericResponse)
async def review_history(
    title: str | None = Query(None, max_length=255),
    status: Literal["pending", "processing", "cancelling", "completed", "cancelled", "failed"] | None = None,
    file_id: int | None = Query(None, ge=1),
    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100),
    db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    from app.services.review_history import list_history

    return GenericResponse(data=await list_history(
        db, current_user.id, title=title, status=status, file_id=file_id, page=page, page_size=page_size,
    ))


@router.get("/history/{history_id}", response_model=GenericResponse)
async def review_history_detail(
    history_id: str, db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    from app.services.review_history import history_detail

    return GenericResponse(data=await history_detail(db, current_user.id, history_id))


@router.post("/jobs", response_model=GenericResponse, status_code=202)
async def start_background_review(
    request: ReviewStartRequest,
    current_user: User = Depends(get_current_user),
):
    from app.services.review_jobs import start_job

    return GenericResponse(data=await start_job(request, current_user))


@router.get("/jobs", response_model=GenericResponse)
async def list_review_jobs(
    limit: int = Query(20, ge=1, le=100),
    db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    from app.services.review_jobs import ACTIVE, job_data, reconcile

    jobs = db.query(ReviewJob).filter_by(user_id=current_user.id).order_by(
        ReviewJob.status.in_(ACTIVE).desc(), ReviewJob.created_at.desc(), ReviewJob.id.desc(),
    ).limit(limit).all()
    return GenericResponse(data=[job_data(await reconcile(job, db)) for job in jobs])


def _owned_job(job_id, db, user):
    job = db.get(ReviewJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "Review task not found")
    return job


@router.get("/jobs/{job_id}", response_model=GenericResponse)
async def review_job_status(
    job_id: str, db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    from app.services.review_jobs import job_data, reconcile

    return GenericResponse(data=job_data(await reconcile(_owned_job(job_id, db, current_user), db)))


@router.post("/jobs/{job_id}/cancel", response_model=GenericResponse)
async def stop_background_review(
    job_id: str, db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    from app.services.review_jobs import cancel_job

    return GenericResponse(data=await cancel_job(_owned_job(job_id, db, current_user), db))


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
        .join(ReviewTask, ReviewTask.id == ReviewResult.task_id)
        .filter(
            ReviewTask.user_id == current_user.id,
            ReviewResult.task_id == request.task_id,
            ReviewResult.session_id == request.session_id,
            ReviewResult.index == request.index,
        )
        .first()
    )
    if result is None:
        raise HTTPException(404, "Risk point not found")
    result.is_accepted = request.is_accepted
    for job in db.query(ReviewJob).filter_by(session_id=request.session_id, user_id=current_user.id):
        if job.snapshot.get("task_id") == request.task_id:
            job.snapshot = {**job.snapshot, "risk_points": [
                {**point, "is_accepted": request.is_accepted} if point.get("id") == result.id else point
                for point in job.snapshot.get("risk_points", [])
            ]}
    db.commit()
    return GenericResponse(msg="ok", data=True)


@router.post("/contracts/accept", response_model=GenericResponse)
async def accept_contract_file(
    request: AcceptContractFileRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.get(ContractFile, request.file_id)
    if record is None or record.user_id != current_user.id:
        raise HTTPException(404, "Contract file not found")
    record.is_accepted = request.is_accepted
    db.commit()
    return GenericResponse(msg="ok", data=True)
