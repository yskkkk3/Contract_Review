"""Paginated history for background reviews and surviving pre-background results."""
from datetime import UTC

from fastapi import HTTPException
from sqlalchemy import exists, func, null, select, union_all

from app.models.contract import ContractFile
from app.models.review import ReviewJob, ReviewResult, ReviewTask
from app.models.session_message import Session
from app.services.review_jobs import ACTIVE, job_data, reconcile


def history_time(value):
    return value.replace(tzinfo=UTC).isoformat() if value and value.tzinfo is None else (
        value.isoformat() if value else None
    )


def _owned_query(model, user_id):
    return select(model).join(ContractFile, ContractFile.id == model.file_id).join(
        Session, Session.id == model.session_id,
    ).where(model.user_id == user_id, ContractFile.user_id == user_id, Session.user_id == user_id)


def _legacy_data(task, contract, points):
    return {
        "id": f"legacy-{task.id}", "task_id": task.id, "session_id": task.session_id,
        "file_id": task.file_id, "title": contract.title, "status": task.status,
        "stance": task.stance, "intensity": task.intensity, "description": task.description,
        "contract_type": task.contract_type, "created_at": history_time(task.created_at),
        "completed_at": history_time(task.completed_at), "summary": None, "chunk_count": 0,
        "error": "", "risk_points": [{
            "id": point.id, "task_id": point.task_id, "session_id": point.session_id,
            "index": point.index, "original_content": point.original_content,
            "risk_analysis": point.risk_analysis, "risk_level": point.risk_level,
            "suggested_content": point.suggested_content, "risk_dim": point.risk_dim,
            "is_accepted": point.is_accepted,
        } for point in points],
    }


def _metadata(data, contract, risk_count=None):
    summary = data.get("summary") or {}
    return {
        key: data.get(key) for key in (
            "id", "session_id", "file_id", "title", "status", "stance", "intensity",
            "contract_type", "created_at", "completed_at",
        )
    } | {
        "risk_point_count": (len(data.get("risk_points", [])) if risk_count is None else risk_count)
        if data["status"] == "completed" else None,
        "overall_risk": summary.get("overall_risk"), "review_status": summary.get("review_status"),
        "can_repeat": contract.parse_status == "parsed" and data["status"] not in ACTIVE,
    }


async def list_history(db, user_id, *, title=None, status=None, file_id=None, page=1, page_size=10):
    # Reconcile before counting/filtering, so interrupted jobs do not appear active forever.
    active = _owned_query(ReviewJob, user_id).where(ReviewJob.status.in_(ACTIVE))
    if file_id is not None:
        active = active.where(ReviewJob.file_id == file_id)
    for job in db.scalars(active).all():
        await reconcile(job, db)

    jobs = _owned_query(ReviewJob, user_id)
    tasks = _owned_query(ReviewTask, user_id).where(~exists(select(ReviewJob.id).where(
        ReviewJob.session_id == ReviewTask.session_id,
        ReviewJob.snapshot["task_id"].as_integer() == ReviewTask.id,
    )))
    for model, query in ((ReviewJob, jobs), (ReviewTask, tasks)):
        if title and title.strip():
            query = query.where(ContractFile.title.contains(title.strip(), autoescape=True))
        if status:
            query = query.where(model.status == status)
        if file_id is not None:
            query = query.where(model.file_id == file_id)
        if model is ReviewJob:
            jobs = query.with_only_columns(
                ReviewJob.id.label("job_id"), null().label("task_id"),
                ReviewJob.created_at.label("created_at"),
            )
        else:
            tasks = query.with_only_columns(
                null().label("job_id"), ReviewTask.id.label("task_id"),
                ReviewTask.created_at.label("created_at"),
            )
    # Keep string job IDs and integer legacy IDs in separate UNION columns.
    # CONCAT/CAST inherits the connection collation, which can differ from the
    # review_jobs.id column and make even COUNT(*) fail with MySQL error 1271.
    combined = union_all(jobs, tasks).subquery()
    total = db.scalar(select(func.count()).select_from(combined))
    keys = db.execute(select(combined.c.job_id, combined.c.task_id).order_by(
        combined.c.created_at.desc(), combined.c.job_id.desc(), combined.c.task_id.desc(),
    ).offset((page - 1) * page_size).limit(page_size)).all()
    ids = [job_id if job_id is not None else f"legacy-{task_id}" for job_id, task_id in keys]
    # Batch page metadata; legacy risk bodies are loaded only when details are opened.
    indexed = {}
    job_rows = db.execute(select(ReviewJob, ContractFile).join(
        ContractFile, ContractFile.id == ReviewJob.file_id,
    ).where(ReviewJob.id.in_(ids))).all()
    for job, contract in job_rows:
        data = {**job_data(job), "created_at": history_time(job.created_at),
                "completed_at": history_time(job.completed_at)}
        indexed[job.id] = _metadata(data, contract)
    legacy_ids = [int(value.removeprefix("legacy-")) for value in ids
                  if value.startswith("legacy-") and value not in indexed]
    counts = dict(db.execute(select(ReviewResult.task_id, func.count()).where(
        ReviewResult.task_id.in_(legacy_ids),
    ).group_by(ReviewResult.task_id)).all())
    for task, contract in db.execute(select(ReviewTask, ContractFile).join(
        ContractFile, ContractFile.id == ReviewTask.file_id,
    ).where(ReviewTask.id.in_(legacy_ids))).all():
        data = _legacy_data(task, contract, [])
        indexed[data["id"]] = _metadata(data, contract, counts.get(task.id, 0))
    items = [indexed[value] for value in ids if value in indexed]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def history_detail(db, user_id, history_id):
    job = db.scalar(_owned_query(ReviewJob, user_id).where(ReviewJob.id == history_id))
    if job is not None:
        await reconcile(job, db)
        contract = db.get(ContractFile, job.file_id)
        data = {**job_data(job), "created_at": history_time(job.created_at),
                "completed_at": history_time(job.completed_at), "notice": job.snapshot.get("notice", "")}
    elif history_id.startswith("legacy-"):
        number = history_id.removeprefix("legacy-")
        if not number.isascii() or not number.isdigit() or len(number) > 18:
            raise HTTPException(404, "Review history not found")
        task = db.scalar(_owned_query(ReviewTask, user_id).where(ReviewTask.id == int(number)))
        if task is None:
            raise HTTPException(404, "Review history not found")
        contract = db.get(ContractFile, task.file_id)
        points = db.scalars(select(ReviewResult).where(
            ReviewResult.task_id == task.id,
        ).order_by(ReviewResult.index, ReviewResult.id)).all()
        data = _legacy_data(task, contract, points)
        data["notice"] = "这次审阅未保存摘要，仅展示已保存的风险点和审阅配置。"
    else:
        raise HTTPException(404, "Review history not found")
    return {**data, "can_repeat": contract.parse_status == "parsed" and data["status"] not in ACTIVE}


def archive_replaced_reviews(db, session_id, current_task_id, user_id):
    """Archive legacy results in the same transaction as a successful replacement."""
    represented = set(db.scalars(select(ReviewJob.snapshot["task_id"].as_integer()).where(
        ReviewJob.session_id == session_id,
    )))
    tasks = db.scalars(select(ReviewTask).where(
        ReviewTask.session_id == session_id, ReviewTask.id != current_task_id,
        ReviewTask.user_id == user_id, ReviewTask.status != "processing",
    )).all()
    for task in tasks:
        if task.id in represented:
            continue
        contract = db.get(ContractFile, task.file_id)
        if contract is None or contract.user_id != user_id:
            continue
        points = db.scalars(select(ReviewResult).where(
            ReviewResult.task_id == task.id,
        ).order_by(ReviewResult.index, ReviewResult.id)).all()
        snapshot = _legacy_data(task, contract, points)
        snapshot["notice"] = "这次审阅未保存摘要，仅展示已保存的风险点和审阅配置。"
        db.add(ReviewJob(
            id=snapshot["id"], user_id=user_id, session_id=session_id, file_id=task.file_id,
            status=task.status, snapshot=snapshot, created_at=task.created_at,
            completed_at=task.completed_at,
        ))
