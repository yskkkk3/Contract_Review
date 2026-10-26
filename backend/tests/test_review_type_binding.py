"""Step 2: saved type controls both prompt scope and the actual review state."""
import json

import pytest

from app.core.db import SessionLocal
from app.models.contract import ContractFile, ContractType
from app.models.review import ReviewJob, ReviewTask
from tests.test_priority_fixes import contract as contract


def assign_type(file_id, name, active=True):
    with SessionLocal() as db:
        item = db.query(ContractType).filter_by(name=name).one()
        item.is_active = int(active)
        db.get(ContractFile, file_id).contract_type_id = item.id
        db.commit()


def session(client, headers, file_id):
    return client.post("/api/sessions", headers=headers, json={
        "title": "type binding", "session_type": "review", "file_id": file_id,
    }).json()["data"]["session_id"]


def test_saved_type_drives_graph_even_if_client_omits_it(client, auth_headers, contract, monkeypatch):
    from app.agent.prompts import load_prompt
    from app.services import review_service

    seen = []

    class Graph:
        async def astream(self, state, **kwargs):
            seen.append((state["contract_type"], load_prompt("specialist_base", risk_dim="验收交付与质保")))
            yield "updates", {"arbitration": {"final_risk_points": [], "summary": {"review_status": "completed"}}}

    monkeypatch.setattr(review_service, "get_graph", lambda _: Graph())
    monkeypatch.setattr(review_service, "get_rag_service", lambda: object())
    assign_type(contract[0], "信息化项目")
    sid = session(client, auth_headers, contract[0])
    response = client.post("/api/reviews/start", headers=auth_headers, json={"session_id": sid, "stance": "甲方"})
    assert response.status_code == 200
    events = [json.loads(frame[6:]) for frame in response.text.split("\n\n") if frame]
    assert events[-1]["event"] == "end"
    assert events[0]["data"]["review_scope"]["profile_id"] == "technology"
    assert events[-1]["data"]["review_scope"]["version"] == "1"
    assert seen[0][0] == "信息化项目"
    assert "technology.deliverables" in seen[0][1]
    with SessionLocal() as db:
        assert db.query(ReviewTask).one().contract_type == "信息化项目"


@pytest.mark.parametrize(("saved", "requested", "active"), [
    ("信息化项目", "租赁服务", True), ("信息化项目", "", False),
])
def test_invalid_type_binding_is_rejected_before_start(client, auth_headers, contract, saved, requested, active):
    assign_type(contract[0], saved, active)
    sid = session(client, auth_headers, contract[0])
    response = client.post("/api/reviews/jobs", headers=auth_headers,
                           json={"session_id": sid, "stance": "甲方", "contract_type": requested})
    assert response.status_code == 422
    with SessionLocal() as db:
        assert db.query(ReviewTask).count() == db.query(ReviewJob).count() == 0


def test_background_history_retains_applied_scope_after_contract_type_changes(
    client, auth_headers, contract, monkeypatch,
):
    from app.agent.review_profiles import PROFILES, assessed_scope
    from app.services import review_service
    from tests.test_review_jobs import wait_status

    class Graph:
        async def astream(self, state, **kwargs):
            records = [{"check_id": check.id, "status": "reviewed", "reason": "已保存的核对记录", "clause_indices": [0]}
                       for check in PROFILES[state["contract_type"]].checks]
            scope = assessed_scope(state["contract_type"], [{"check_results": records}])
            yield "updates", {"arbitration": {"final_risk_points": [], "summary": {
                "review_status": "completed", "review_scope": scope,
            }}}

    monkeypatch.setattr(review_service, "get_graph", lambda _: Graph())
    monkeypatch.setattr(review_service, "get_rag_service", lambda: object())
    assign_type(contract[0], "信息化项目")
    sid = session(client, auth_headers, contract[0])
    response = client.post("/api/reviews/jobs", headers=auth_headers, json={"session_id": sid, "stance": "甲方"})
    assert response.status_code == 202
    job = response.json()["data"]
    assert job["contract_type"] == "信息化项目"
    assert job["review_scope"]["checklist_status"] == "configured"
    saved = wait_status(client, auth_headers, job["id"], "completed")
    assert saved["review_scope"]["checklist_status"] == "reviewed"
    assign_type(contract[0], "租赁服务")
    history = client.get(f"/api/reviews/history/{job['id']}", headers=auth_headers).json()["data"]
    assert history["review_scope"]["profile_name"] == "信息化项目"
    assert len(history["review_scope"]["check_results"]) == 4
    assert history["summary"]["review_scope"] == history["review_scope"]


def test_legacy_history_does_not_invent_a_current_scope(client, auth_headers, contract):
    from tests.test_priority_fixes import seed_review, user_id

    with SessionLocal() as db:
        _, tid = seed_review(db, user_id(auth_headers), contract[0])
    assign_type(contract[0], "信息化项目")
    history = client.get(f"/api/reviews/history/legacy-{tid}", headers=auth_headers).json()["data"]
    assert history.get("review_scope") is None


def test_untyped_file_cannot_select_a_disabled_profile(client, auth_headers, contract):
    with SessionLocal() as db:
        db.query(ContractType).filter_by(name="信息化项目").one().is_active = 0
        db.commit()
    sid = session(client, auth_headers, contract[0])
    response = client.post("/api/reviews/jobs", headers=auth_headers, json={
        "session_id": sid, "stance": "甲方", "contract_type": "信息化项目",
    })
    assert response.status_code == 422
    with SessionLocal() as db:
        assert db.query(ReviewJob).count() == 0
