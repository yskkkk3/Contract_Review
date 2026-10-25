"""History pagination, filtering, ownership, legacy results and atomic archives."""
from datetime import datetime, timedelta

import pytest

from app.core.db import SessionLocal
from app.models.contract import ContractFile
from app.models.review import ReviewJob, ReviewResult, ReviewTask
from app.models.session_message import Session, SessionTypeEnum
from app.models.user import User
from tests.test_priority_fixes import contract as contract
from tests.test_priority_fixes import other_headers as other_headers
from tests.test_priority_fixes import seed_review, user_id


def add_job(db, owner, file_id, number=0, status="completed"):
    session = Session(user_id=owner, file_id=file_id, session_type=SessionTypeEnum.REVIEW, title="history")
    db.add(session)
    db.flush()
    task = ReviewTask(user_id=owner, file_id=file_id, session_id=session.id, status=status)
    db.add(task)
    db.flush()
    point = ReviewResult(task_id=task.id, session_id=session.id, index=1, original_content="Saved clause", is_accepted=1)
    db.add(point)
    db.flush()
    job = ReviewJob(
        id=f"job-{number}", user_id=owner, file_id=file_id, session_id=session.id, status=status,
        created_at=datetime(2026, 10, 1) + timedelta(hours=number),
        completed_at=datetime(2026, 10, 1, 0, 5) + timedelta(hours=number),
        snapshot={
            "task_id": task.id, "title": db.get(ContractFile, file_id).title,
            "stance": "乙方", "intensity": "严格", "description": "关注付款条款",
            "contract_type": "采购", "summary": {
                "summary": "Saved conclusion", "suggestion": "Saved suggestion",
                "overall_risk": "中", "review_status": "completed",
            } if status == "completed" else None,
            "risk_points": [{"id": point.id, "task_id": task.id, "session_id": session.id,
                             "index": 1, "original_content": point.original_content, "is_accepted": 1}],
        },
    )
    db.add(job)
    return job


def test_history_pages_beyond_recent_twenty_without_duplicate_tasks(client, auth_headers, contract):
    with SessionLocal() as db:
        for number in range(25):
            add_job(db, user_id(auth_headers), contract[0], number)
        db.commit()
    data = client.get("/api/reviews/history", headers=auth_headers,
                      params={"page": 3, "page_size": 10}).json()["data"]
    assert data["total"] == 25
    assert [row["id"] for row in data["items"]] == [f"job-{number}" for number in range(4, -1, -1)]
    assert data["items"][0]["risk_point_count"] == 1
    assert data["items"][0]["overall_risk"] == "中"
    assert data["items"][0]["created_at"].endswith("+00:00")
    assert "risk_points" not in data["items"][0]
    assert client.get("/api/reviews/history", headers=auth_headers, params={"page": 99}).json()["data"]["items"] == []


def test_mysql_history_union_keeps_text_and_numeric_ids_separate(client, auth_headers, contract):
    from sqlalchemy import event
    from sqlalchemy.dialects import mysql

    from app.core.db import engine

    with SessionLocal() as db:
        add_job(db, user_id(auth_headers), contract[0], 1)
        _, tid = seed_review(db, user_id(auth_headers), contract[0])
        db.commit()
    statements = []

    def capture(conn, clause, multiparams, params, options):
        sql = str(clause.compile(dialect=mysql.dialect()))
        if "UNION ALL" in sql:
            statements.append(sql)

    event.listen(engine, "before_execute", capture)
    try:
        result = client.get("/api/reviews/history", headers=auth_headers).json()["data"]
    finally:
        event.remove(engine, "before_execute", capture)
    assert result["total"] == 2
    assert {item["id"] for item in result["items"]} == {"job-1", f"legacy-{tid}"}
    assert len(statements) == 2  # Count and pagination use the same safe projections.
    for sql in statements:
        assert "review_jobs.id AS job_id, NULL AS task_id" in sql
        assert "NULL AS job_id, review_tasks.id AS task_id" in sql
        assert "concat(" not in sql.lower()
        assert "AS CHAR" not in sql


def test_history_paginates_mixed_ids_with_identical_timestamps(client, auth_headers, contract):
    timestamp = datetime(2026, 10, 1)
    with SessionLocal() as db:
        job = add_job(db, user_id(auth_headers), contract[0], 1)
        _, tid = seed_review(db, user_id(auth_headers), contract[0])
        job.created_at = timestamp
        db.get(ReviewTask, tid).created_at = timestamp
        db.commit()
    pages = [client.get("/api/reviews/history", headers=auth_headers, params={
        "page": page, "page_size": 1,
    }).json()["data"] for page in (1, 2)]
    assert [page["total"] for page in pages] == [2, 2]
    assert {page["items"][0]["id"] for page in pages} == {"job-1", f"legacy-{tid}"}


def test_history_filters_contract_title_status_and_literal_wildcards(client, auth_headers, contract):
    with SessionLocal() as db:
        record = db.get(ContractFile, contract[0])
        record.title = "采购_100%.docx"
        add_job(db, user_id(auth_headers), contract[0], 1)
        add_job(db, user_id(auth_headers), contract[0], 2, status="cancelled")
        db.commit()
    data = client.get("/api/reviews/history", headers=auth_headers, params={
        "title": "_100%", "status": "completed", "file_id": contract[0],
    }).json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["id"] == "job-1"
    for params in ({"title": "x_100%"}, {"file_id": contract[0] + 100}, {"status": "failed"}):
        assert client.get("/api/reviews/history", headers=auth_headers, params=params).json()["data"]["total"] == 0


def test_history_details_are_private_and_do_not_start_inference(client, auth_headers, other_headers, contract):
    with SessionLocal() as db:
        add_job(db, user_id(auth_headers), contract[0], 1)
        sid, tid = seed_review(db, user_id(auth_headers), contract[0])
        db.commit()
    assert client.get("/api/reviews/history").status_code == 401
    assert client.get("/api/reviews/history", headers=other_headers).json()["data"]["total"] == 0
    for history_id in ("job-1", f"legacy-{tid}"):
        assert client.get(f"/api/reviews/history/{history_id}", headers=other_headers).status_code == 404
    data = client.get("/api/reviews/history/job-1", headers=auth_headers).json()["data"]
    assert data["summary"]["summary"] == "Saved conclusion"
    assert data["description"] == "关注付款条款"
    assert data["risk_points"][0]["is_accepted"] == 1
    assert data["can_repeat"] is True
    with SessionLocal() as db:
        assert db.query(ReviewTask).count() == 2


def test_legacy_results_have_no_fabricated_summary(client, auth_headers, contract):
    with SessionLocal() as db:
        _, tid = seed_review(db, user_id(auth_headers), contract[0])
    listing = client.get("/api/reviews/history", headers=auth_headers).json()["data"]
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == f"legacy-{tid}"
    assert listing["items"][0]["overall_risk"] is None
    detail = client.get(f"/api/reviews/history/legacy-{tid}", headers=auth_headers).json()["data"]
    assert detail["summary"] is None
    assert "未保存摘要" in detail["notice"]
    assert detail["risk_points"][0]["original_content"] == "previous result"


def test_history_reconciles_lost_jobs_before_filtering(client, auth_headers, contract, monkeypatch):
    from app.services import review_jobs

    with SessionLocal() as db:
        add_job(db, user_id(auth_headers), contract[0], 1, status="processing")
        db.commit()
    monkeypatch.setattr(review_jobs, "SessionLocal", lambda: pytest.fail("Reconciliation must use the request transaction"))
    active = client.get("/api/reviews/history", headers=auth_headers, params={"status": "processing"}).json()["data"]
    assert active["total"] == 0
    failed = client.get("/api/reviews/history", headers=auth_headers, params={"status": "failed"}).json()["data"]
    assert failed["total"] == 1
    assert failed["items"][0]["risk_point_count"] is None


def test_legacy_task_cannot_expose_another_users_contract(client, auth_headers, other_headers, contract):
    with SessionLocal() as db:
        foreign = ContractFile(user_id=user_id(other_headers), title="private.docx", file_type="docx",
                               file_path=str(contract[1]), content_path=str(contract[2]), parse_status="parsed")
        db.add(foreign)
        db.flush()
        _, tid = seed_review(db, user_id(auth_headers), foreign.id)
    assert client.get("/api/reviews/history", headers=auth_headers).json()["data"]["total"] == 0
    assert client.get(f"/api/reviews/history/legacy-{tid}", headers=auth_headers).status_code == 404


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page_size": 0}, {"page_size": 101}, {"file_id": 0}, {"status": "invalid"},
])
def test_history_validates_queries(client, auth_headers, params):
    assert client.get("/api/reviews/history", headers=auth_headers, params=params).status_code == 422


@pytest.mark.parametrize("history_id", ["legacy--1", "legacy-abc", "legacy-" + "9" * 30, "unknown"])
def test_invalid_history_ids_are_not_found(client, auth_headers, history_id):
    assert client.get(f"/api/reviews/history/{history_id}", headers=auth_headers).status_code == 404


async def test_replacement_keeps_old_result_in_history(client, auth_headers, contract, monkeypatch):
    from app.schemas.review import ReviewStartRequest
    from app.services import review_service

    class Graph:
        async def astream(self, *args, **kwargs):
            yield "updates", {"arbitration": {
                "final_risk_points": [{"original_content": "replacement"}],
                "summary": {"review_status": "completed"},
            }}

    monkeypatch.setattr(review_service, "get_graph", lambda _: Graph())
    with SessionLocal() as db:
        sid, tid = seed_review(db, user_id(auth_headers), contract[0])
        response = await review_service.stream_review_events(
            ReviewStartRequest(session_id=sid, stance="甲方"),
            db.get(User, user_id(auth_headers)), db, rag=object(),
        )
        async for _ in response.body_iterator:
            pass
        assert db.get(ReviewTask, tid) is None
        assert [point.original_content for point in db.query(ReviewResult).all()] == ["replacement"]
    previous = client.get(f"/api/reviews/history/legacy-{tid}", headers=auth_headers).json()["data"]
    assert previous["risk_points"][0]["original_content"] == "previous result"
    listing = client.get("/api/reviews/history", headers=auth_headers).json()["data"]
    assert listing["total"] == 2
