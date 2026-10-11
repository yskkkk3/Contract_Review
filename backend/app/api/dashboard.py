"""Dashboard stats routes."""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db
from app.models.contract import ContractFile
from app.models.review import ReviewResult, ReviewTask
from app.models.session_message import Session
from app.models.user import User
from app.schemas.base import GenericResponse
from app.schemas.dashboard import (
    DepartmentUsageItem,
    OverviewResponse,
    RevisionsResponse,
    TrendItem,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=GenericResponse[OverviewResponse])
async def overview(db: DBSession = Depends(get_db)):
    reviewed = db.query(ReviewTask).filter(ReviewTask.status == "completed").count()
    users = db.query(User).count()
    amount = (
        db.query(func.coalesce(func.sum(ContractFile.amount), 0.0))
        .filter(ContractFile.amount > 0)
        .scalar()
        or 0.0
    )
    return GenericResponse(
        data=OverviewResponse(
            reviewed_contracts=reviewed, service_departments=1, users_count=users,
            served_faculty_students=users, total_reviewed_amount=float(amount),
        )
    )


@router.get("/revisions", response_model=GenericResponse[RevisionsResponse])
async def revisions(db: DBSession = Depends(get_db)):
    risk = db.query(ReviewResult).filter(ReviewResult.is_accepted == 1).count()
    return GenericResponse(data=RevisionsResponse(risk_points_revised=risk, error_points_revised=0))


@router.get("/trends", response_model=GenericResponse[list[TrendItem]])
async def trends(period: str = "month", db: DBSession = Depends(get_db)):
    """按 period 聚合审阅趋势（跨方言：取数后在 Python 侧格式化分组）。"""
    from collections import defaultdict

    rows = (
        db.query(ReviewTask.created_at)
        .filter(ReviewTask.status == "completed")
        .all()
    )
    fmt = {"day": "%Y-%m-%d", "week": "%Y-W%W", "month": "%Y-%m", "year": "%Y"}.get(period, "%Y-%m")
    counter: dict[str, int] = defaultdict(int)
    for (dt,) in rows:
        counter[dt.strftime(fmt)] += 1
    return GenericResponse(
        data=[TrendItem(date=d, total=c) for d, c in sorted(counter.items())]
    )


@router.get("/departments", response_model=GenericResponse[list[DepartmentUsageItem]])
async def departments(db: DBSession = Depends(get_db)):
    """按部门聚合（高校场景：按用户名前缀模拟部门，后续可接组织表）。"""
    rows = (
        db.query(User.username, func.count(Session.id))
        .join(Session, Session.user_id == User.id)
        .group_by(User.username)
        .all()
    )
    items = [
        DepartmentUsageItem(
            department_name=name or "未分配",
            contract_review=0, contract_verification=0, contract_comparison=int(cnt), total=int(cnt),
        )
        for name, cnt in rows
    ]
    return GenericResponse(data=items)
