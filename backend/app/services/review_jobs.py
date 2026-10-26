"""Background reviews with durable snapshots and cross-worker cancellation/leases.

Workers run in the API process. Browser disconnects do not stop them. A lost worker
is reported as interrupted rather than leaving a task permanently in progress.
"""
import asyncio
import json
import logging
from contextlib import aclosing
from datetime import UTC, datetime
from uuid import uuid4

from anyio import CancelScope
from fastapi import HTTPException
from sqlalchemy import select

from app.agent.review_profiles import review_scope
from app.core.cache import acquire_lock, release_lock, renew_lock
from app.core.db import SessionLocal
from app.core.redis import get_redis
from app.models.review import ReviewJob, ReviewTask
from app.services.review_service import resolve_review_type, stream_review_events

logger = logging.getLogger(__name__)
ACTIVE = ("processing", "cancelling")
LEASE_SECONDS = 30
_workers: dict[str, asyncio.Task] = {}


def _lease(job):
    return f"review_job:file:{job.user_id}:{job.file_id}"


def _cancel_key(job_id):
    return f"review_job:cancel:{job_id}"


def job_data(job):
    return {
        **job.snapshot, "id": job.id, "session_id": job.session_id,
        "file_id": job.file_id, "status": job.status,
        "created_at": job.created_at.isoformat(),
    }


def _finish(job_id, status, error="", *, db=None):
    if db is None:
        with SessionLocal() as owned_db:
            return _finish(job_id, status, error, db=owned_db)
    job = db.scalars(select(ReviewJob).where(ReviewJob.id == job_id).with_for_update()
                     .execution_options(populate_existing=True)).first()
    task_id = None
    if job is not None and job.status in ACTIVE:
        job.status = status
        job.completed_at = datetime.now(UTC)
        job.snapshot = {**job.snapshot, "error": error}
        task_id = job.snapshot.get("task_id")
    db.commit()
    if task_id:
        # Release the job row before updating the engine task. Finalization flushes
        # task rows before locking the job; reversing that order can deadlock MySQL.
        db.query(ReviewTask).filter(ReviewTask.id == task_id, ReviewTask.status == "processing").update({
            "status": "cancelled" if status == "cancelled" else "failed",
            "completed_at": datetime.now(UTC),
        }, synchronize_session=False)
        db.commit()


async def reconcile(job, db):
    if job.status in ACTIVE and await get_redis().get(_lease(job)) != job.id:
        # Commit in this request's transaction: a separate commit remains invisible
        # to an existing MySQL REPEATABLE READ snapshot, including status filters.
        _finish(job.id, "failed", "后台服务中断，本次审阅未完成，请重新发起", db=db)
        db.refresh(job)
    return job


async def start_job(request, user):
    # The worker owns this session. Never retain a request-scoped DB session.
    worker_db = SessionLocal()
    response = None
    job = None
    lease_owned = False
    lease_key = ""
    try:
        job_id = uuid4().hex

        def complete(task, records, summary):
            # Serialize completion against cancellation, including requests on another worker.
            job = worker_db.scalars(select(ReviewJob).where(ReviewJob.id == job_id).with_for_update()
                                    .execution_options(populate_existing=True)).one()
            if job.status != "processing":
                raise asyncio.CancelledError
            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            job.snapshot = {**job.snapshot, "task_id": task.id, "summary": summary, "error": "",
                            "review_scope": summary.get("review_scope") or job.snapshot.get("review_scope"), "risk_points": [{
                "id": point.id, "task_id": task.id, "session_id": task.session_id,
                "index": point.index, "original_content": point.original_content,
                "risk_analysis": point.risk_analysis, "risk_level": point.risk_level,
                "suggested_content": point.suggested_content, "risk_dim": point.risk_dim,
                "is_accepted": point.is_accepted,
            } for point in records]}

        response = await stream_review_events(
            request, user, worker_db, lock_token=job_id, on_complete=complete,
            commit_guard=lambda: renew_lock(lease_key, job_id, ttl=LEASE_SECONDS),
        )
        from app.models.contract import ContractFile
        from app.models.session_message import Session

        session = worker_db.get(Session, request.session_id)
        contract = worker_db.get(ContractFile, session.file_id)
        contract_type, _ = resolve_review_type(worker_db, contract, request.contract_type)
        job = ReviewJob(
            id=job_id, user_id=user.id, session_id=session.id, file_id=contract.id,
            status="processing", snapshot={
                "title": contract.title, "stance": request.stance,
                "intensity": request.intensity, "description": request.description or "",
                "contract_type": contract_type, "risk_points": [],
                "supplement_file_ids": list(dict.fromkeys(request.supplement_file_ids)),
                "material_decision": None,
                "review_scope": review_scope(contract_type),
                "summary": None, "chunk_count": 0, "error": "",
            },
        )
        lease_key = _lease(job)
        lease_owned = await acquire_lock(lease_key, job.id, ttl=LEASE_SECONDS)
        if not lease_owned:
            raise HTTPException(409, "该合同已有后台审阅进行中，请先查看或停止现有任务")
        worker_db.add(job)
        worker_db.commit()
        worker_db.refresh(job)
        data = job_data(job)
        # create_task copies the runtime configuration ContextVars before request cleanup.
        task = asyncio.create_task(_run(job.id, _lease(job), response, worker_db))
        _workers[job.id] = task
        task.add_done_callback(lambda done, key=job.id: _worker_done(key, done))
        return data
    except BaseException:
        worker_db.rollback()
        if response is not None:
            await response.body_iterator.aclose()
        if lease_owned:
            await release_lock(_lease(job), job.id)
        worker_db.close()
        raise


def _worker_done(job_id, task):
    _workers.pop(job_id, None)
    if not task.cancelled() and task.exception() is not None:
        error = task.exception()
        logger.error("Background review failed job_id=%s", job_id,
                     exc_info=(type(error), error, error.__traceback__))


async def _consume(job_id, response):
    async with aclosing(response.body_iterator) as frames:
        async for frame in frames:
            event = json.loads(frame[6:])
            with SessionLocal() as db:
                job = db.get(ReviewJob, job_id)
                if job is None:
                    raise RuntimeError("Background review record disappeared")
                if job.status == "completed":
                    continue
                if job.status == "cancelling":
                    raise asyncio.CancelledError
                snapshot = dict(job.snapshot)
                kind, data = event["event"], event["data"]
                if kind == "meta":
                    snapshot.update(data)
                elif kind == "message":
                    # Final persisted messages replace provisional specialist output.
                    points = list(snapshot["risk_points"])
                    if data.get("id") and not snapshot.get("final_points_started"):
                        points = []
                        snapshot["final_points_started"] = True
                    points.append(data)
                    snapshot["risk_points"] = points
                elif kind == "end":
                    snapshot["risk_points"] = [p for p in snapshot["risk_points"] if p.get("id")]
                    snapshot["summary"] = data
                    snapshot["review_scope"] = data.get("review_scope") or snapshot.get("review_scope")
                    job.status = "completed"
                    job.completed_at = datetime.now(UTC)
                elif kind == "error":
                    snapshot["error"] = data["message"]
                    job.status = "failed"
                    job.completed_at = datetime.now(UTC)
                job.snapshot = snapshot
                db.commit()


async def _monitor(job_id, lease_key):
    ticks = 0
    while True:
        await asyncio.sleep(0.5)
        if await get_redis().get(_cancel_key(job_id)):
            return "cancelled"
        ticks += 1
        if ticks % 10 == 0:
            if not await renew_lock(lease_key, job_id, ttl=LEASE_SECONDS):
                raise RuntimeError("后台任务失去执行权，请重新发起审阅")
            with SessionLocal() as db:
                job = db.get(ReviewJob, job_id)
                session_id = job.session_id
            # Also renew the original review engine's commit lease for long reviews.
            session_key = f"review_lock:{session_id}"
            if not await renew_lock(session_key, job_id, ttl=900):
                raise RuntimeError("后台任务失去审阅锁，请重新发起审阅")


async def _run(job_id, lease_key, response, worker_db):
    consumer = asyncio.create_task(_consume(job_id, response))
    monitor = asyncio.create_task(_monitor(job_id, lease_key))
    try:
        done, _ = await asyncio.wait((consumer, monitor), return_when=asyncio.FIRST_COMPLETED)
        if consumer in done:
            await consumer
            _finish(job_id, "failed", "审阅未返回最终结论，请重新发起")
        else:
            await monitor
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)
            _finish(job_id, "cancelled")
    except asyncio.CancelledError:
        with SessionLocal() as db:
            requested = db.get(ReviewJob, job_id).status == "cancelling"
        _finish(job_id, "cancelled" if requested else "failed",
                "" if requested else "后台服务中断，本次审阅未完成，请重新发起")
    except Exception:
        logger.exception("Review execution failed job_id=%s", job_id)
        _finish(job_id, "failed", "审阅执行失败，请重新发起")
    finally:
        with CancelScope(shield=True):
            try:
                consumer.cancel()
                monitor.cancel()
                await asyncio.gather(consumer, monitor, return_exceptions=True)
                await response.body_iterator.aclose()
            finally:
                worker_db.close()
                try:
                    await release_lock(lease_key, job_id)
                finally:
                    await get_redis().delete(_cancel_key(job_id))


async def cancel_job(job, db):
    await reconcile(job, db)
    if job.status not in ACTIVE:
        return job_data(job)
    db.query(ReviewJob).filter(ReviewJob.id == job.id, ReviewJob.status.in_(ACTIVE)).update(
        {"status": "cancelling"}, synchronize_session=False,
    )
    db.commit()
    db.refresh(job)
    if job.status in ACTIVE:
        await get_redis().set(_cancel_key(job.id), "1", ex=3600)
        # The monitor handles requests arriving at another API worker.
    return job_data(job)


async def shutdown_review_jobs():
    tasks = list(_workers.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
