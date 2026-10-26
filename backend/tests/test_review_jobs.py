"""Background reviews survive request completion and cancel across API workers."""
import asyncio
import threading
import time

import pytest

from app.core.db import SessionLocal
from app.models.review import ReviewJob, ReviewTask
from tests.test_priority_fixes import contract as contract
from tests.test_priority_fixes import foreign_keys as foreign_keys
from tests.test_priority_fixes import other_headers as other_headers


@pytest.fixture()
def graph(monkeypatch):
    from app.services import review_service

    class Graph:
        started = threading.Event()
        release = threading.Event()
        closed = threading.Event()
        fail = False

        async def astream(self, *args, **kwargs):
            from app.core.runtime_config import model_config

            self.runtime = model_config("review")
            self.state = args[0]
            self.started.set()
            try:
                yield "custom", {"type": "risk_point", "risk_dim": "付款", "points": [{
                    "original_content": "preview", "risk_analysis": "check", "risk_level": "中",
                }]}
                while not self.release.is_set():
                    await asyncio.sleep(0.02)
                if self.fail:
                    raise RuntimeError("Model unavailable")
                yield "updates", {"arbitration": {
                    "final_risk_points": [{"original_content": "final", "risk_level": "中"}],
                    "summary": {"summary": "Saved summary", "review_status": "completed"},
                }}
            finally:
                self.closed.set()

    instance = Graph()
    monkeypatch.setattr(review_service, "get_graph", lambda _: instance)
    monkeypatch.setattr(review_service, "get_rag_service", lambda: object())
    yield instance
    instance.release.set()


def start(client, headers, file_id, supplement_file_ids=None):
    sid = client.post("/api/sessions", headers=headers, json={
        "title": "background", "session_type": "review", "file_id": file_id,
    }).json()["data"]["session_id"]
    return client.post("/api/reviews/jobs", headers=headers, json={
        "session_id": sid,
        "stance": "甲方",
        "supplement_file_ids": supplement_file_ids or [],
    })


def wait_status(client, headers, job_id, status):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        data = client.get(f"/api/reviews/jobs/{job_id}", headers=headers).json()["data"]
        if data["status"] == status:
            return data
        time.sleep(0.02)
    pytest.fail(f"Background review did not reach {status}: {data}")


def test_background_review_returns_early_restores_and_persists(
    client, auth_headers, contract, graph, foreign_keys,
):
    response = start(client, auth_headers, contract[0])
    assert response.status_code == 202
    job = response.json()["data"]
    assert graph.started.wait(2)
    assert not graph.closed.is_set()
    # Using another feature does not hold open, or cancel, the review request.
    assert client.get("/api/contracts", headers=auth_headers).status_code == 200
    restored = client.get("/api/reviews/jobs", headers=auth_headers).json()["data"]
    assert restored[0]["id"] == job["id"]
    assert restored[0]["status"] == "processing"
    assert client.delete(f"/api/sessions/{job['session_id']}", headers=auth_headers).status_code == 409
    graph.release.set()
    completed = wait_status(client, auth_headers, job["id"], "completed")
    assert completed["summary"]["summary"] == "Saved summary"
    assert [p["original_content"] for p in completed["risk_points"]] == ["final"]
    point = completed["risk_points"][0]
    assert point["id"]
    assert client.post("/api/reviews/risk-points/accept", headers=auth_headers, json={
        "task_id": point["task_id"], "session_id": point["session_id"], "index": 1, "is_accepted": 1,
    }).status_code == 200
    saved = client.get(f"/api/reviews/jobs/{job['id']}", headers=auth_headers).json()["data"]
    assert saved["risk_points"][0]["is_accepted"] == 1
    assert client.post(f"/api/reviews/jobs/{job['id']}/cancel", headers=auth_headers).json()["data"]["status"] == "completed"
    assert client.delete(f"/api/sessions/{job['session_id']}", headers=auth_headers).status_code == 200
    with SessionLocal() as db:
        assert db.get(ReviewJob, job["id"]) is None


def test_supplement_material_is_owned_parsed_bounded_and_saved(
    client, auth_headers, other_headers, contract, graph, tmp_path,
):
    from app.models.contract import ContractFile
    from tests.test_priority_fixes import user_id

    supplement_text = tmp_path / "response.txt"
    supplement_text.write_text("第一条 源代码、部署文档和测试报告应随终验交付。", encoding="utf-8")
    with SessionLocal() as db:
        supplement = ContractFile(
            user_id=user_id(auth_headers), title="供应商响应文件.pdf", file_type="pdf",
            file_path=str(supplement_text), content_path=str(supplement_text), parse_status="parsed",
        )
        foreign = ContractFile(
            user_id=user_id(other_headers), title="其他用户附件.pdf", file_type="pdf",
            file_path=str(supplement_text), content_path=str(supplement_text), parse_status="parsed",
        )
        db.add_all([supplement, foreign])
        db.commit()
        supplement_id, foreign_id = supplement.id, foreign.id

    assert start(client, auth_headers, contract[0], [foreign_id]).status_code == 404
    response = start(client, auth_headers, contract[0], [supplement_id, supplement_id])
    assert response.status_code == 202
    job = response.json()["data"]
    assert job["supplement_file_ids"] == [supplement_id]
    assert graph.started.wait(2)
    assert graph.state["supplement_files"] == [{"file_id": supplement_id, "title": "供应商响应文件.pdf"}]
    assert any("【补充材料：供应商响应文件.pdf】" in chunk for chunk in graph.state["chunks"])
    graph.release.set()
    completed = wait_status(client, auth_headers, job["id"], "completed")
    decision = client.post(
        f"/api/reviews/jobs/{job['id']}/materials",
        headers=auth_headers,
        json={"decision": "supplemented", "supplement_file_ids": [supplement_id]},
    )
    assert decision.status_code == 200
    assert decision.json()["data"]["material_decision"] == "supplemented"
    assert client.post(
        f"/api/reviews/jobs/{job['id']}/materials",
        headers=other_headers,
        json={"decision": "deferred"},
    ).status_code == 404
    assert completed["summary"]["summary"] == "Saved summary"


def test_cancel_stops_inference_and_allows_restart(client, auth_headers, contract, graph):
    job = start(client, auth_headers, contract[0]).json()["data"]
    assert graph.started.wait(2)
    assert start(client, auth_headers, contract[0]).status_code == 409
    cancelled = client.post(f"/api/reviews/jobs/{job['id']}/cancel", headers=auth_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelling"
    result = wait_status(client, auth_headers, job["id"], "cancelled")
    assert result["summary"] is None
    assert graph.closed.wait(2)
    with SessionLocal() as db:
        assert db.get(ReviewTask, result["task_id"]).status == "cancelled"
    graph.release.set()
    restarted = start(client, auth_headers, contract[0])
    assert restarted.status_code == 202
    wait_status(client, auth_headers, restarted.json()["data"]["id"], "completed")


def test_background_jobs_are_private(client, auth_headers, other_headers, contract, graph):
    job = start(client, auth_headers, contract[0]).json()["data"]
    assert client.get("/api/reviews/jobs", headers=other_headers).json()["data"] == []
    assert client.get(f"/api/reviews/jobs/{job['id']}", headers=other_headers).status_code == 404
    assert client.post(f"/api/reviews/jobs/{job['id']}/cancel", headers=other_headers).status_code == 404
    assert client.post("/api/reviews/jobs", headers=other_headers, json={
        "session_id": job["session_id"], "stance": "甲方",
    }).status_code == 404
    graph.release.set()
    wait_status(client, auth_headers, job["id"], "completed")


def test_background_failure_is_restorable(client, auth_headers, contract, graph):
    graph.fail = True
    graph.release.set()
    job = start(client, auth_headers, contract[0]).json()["data"]
    result = wait_status(client, auth_headers, job["id"], "failed")
    assert result["error"]
    assert result["summary"] is None


def test_lost_worker_is_not_reported_as_still_running(client, auth_headers, contract):
    sid = client.post("/api/sessions", headers=auth_headers, json={
        "title": "interrupted", "session_type": "review", "file_id": contract[0],
    }).json()["data"]["session_id"]
    with SessionLocal() as db:
        from app.models.session_message import Session

        owner = db.get(Session, sid).user_id
        task = ReviewTask(session_id=sid, file_id=contract[0], user_id=owner, status="processing")
        db.add(task)
        db.flush()
        db.add(ReviewJob(id="lost", user_id=owner, file_id=contract[0], session_id=sid,
                         status="processing", snapshot={"task_id": task.id, "risk_points": []}))
        db.commit()
    result = client.get("/api/reviews/jobs/lost", headers=auth_headers).json()["data"]
    assert result["status"] == "failed"
    assert "中断" in result["error"]
    with SessionLocal() as db:
        assert db.get(ReviewTask, result["task_id"]).status == "failed"
    assert client.delete(f"/api/sessions/{sid}", headers=auth_headers).status_code == 200


def test_cancel_wins_before_result_commit(client, auth_headers, contract, graph):
    from app.models.review import ReviewResult

    job = start(client, auth_headers, contract[0]).json()["data"]
    assert graph.started.wait(2)
    with SessionLocal() as db:
        owner = db.get(ReviewJob, job["id"]).user_id
        previous = ReviewTask(user_id=owner, session_id=job["session_id"], file_id=contract[0], status="completed")
        db.add(previous)
        db.flush()
        db.add(ReviewResult(task_id=previous.id, session_id=job["session_id"], index=1, original_content="previous"))
        db.commit()
    client.post(f"/api/reviews/jobs/{job['id']}/cancel", headers=auth_headers)
    # Finish the graph before the periodic cancellation monitor wakes up.
    graph.release.set()
    wait_status(client, auth_headers, job["id"], "cancelled")
    with SessionLocal() as db:
        assert [p.original_content for p in db.query(ReviewResult).all()] == ["previous"]


def test_shutdown_closes_inference_and_reports_interruption(client, auth_headers, contract, graph):
    from app.services.review_jobs import shutdown_review_jobs

    job = start(client, auth_headers, contract[0]).json()["data"]
    assert graph.started.wait(2)
    client.portal.call(shutdown_review_jobs)
    result = wait_status(client, auth_headers, job["id"], "failed")
    assert "中断" in result["error"]
    assert graph.closed.wait(2)


def test_background_inference_inherits_admin_configuration(client, auth_headers, contract, graph):
    from app.models.model_configs import ModelConfig

    with SessionLocal() as db:
        db.add(ModelConfig(model_type="review", model_name="background-test-model", is_default=1, status="active"))
        db.commit()
    job = start(client, auth_headers, contract[0]).json()["data"]
    assert graph.started.wait(2)
    assert graph.runtime["model_name"] == "background-test-model"
    graph.release.set()
    wait_status(client, auth_headers, job["id"], "completed")


def test_inference_does_not_hold_an_idle_database_transaction(
    client, auth_headers, contract, graph, monkeypatch,
):
    from app.services import review_jobs

    sessions = []

    def factory():
        db = SessionLocal()
        sessions.append(db)
        return db

    monkeypatch.setattr(review_jobs, "SessionLocal", factory)
    job = start(client, auth_headers, contract[0]).json()["data"]
    assert graph.started.wait(2)
    assert not sessions[0].in_transaction()
    graph.release.set()
    wait_status(client, auth_headers, job["id"], "completed")


def test_worker_without_lease_cannot_publish_results(client, auth_headers, contract, graph):
    from app.core.redis import get_redis
    from app.models.review import ReviewResult

    job = start(client, auth_headers, contract[0]).json()["data"]
    assert graph.started.wait(2)
    with SessionLocal() as db:
        owner = db.get(ReviewJob, job["id"]).user_id

    async def replace_owner():
        await get_redis().set(f"review_job:file:{owner}:{contract[0]}", "new-owner", ex=30)

    client.portal.call(replace_owner)
    graph.release.set()
    assert graph.closed.wait(2)
    wait_status(client, auth_headers, job["id"], "failed")
    with SessionLocal() as db:
        assert db.query(ReviewResult).count() == 0
