"""Review-aware chat sessions can explain and challenge persisted review results."""
import json

from app.core.db import SessionLocal
from app.core.security import decode_token
from app.models.contract import ContractFile
from app.models.review import ReviewJob
from app.models.review_chat import ReviewChatContext
from app.models.session_message import Session, SessionTypeEnum


def _user_id(headers):
    return decode_token(headers["Authorization"][7:])["user_id"]


def _seed_completed_review(headers, tmp_path):
    content = tmp_path / "review-chat-contract.txt"
    content.write_text("第二条 甲方应在验收合格后30日内付款。", encoding="utf-8")
    with SessionLocal() as db:
        contract = ContractFile(
            user_id=_user_id(headers), title="信息化服务合同.pdf", file_type="pdf",
            file_path=str(content), content_path=str(content), parse_status="parsed",
        )
        db.add(contract)
        db.flush()
        review_session = Session(
            user_id=_user_id(headers), title="review", session_type=SessionTypeEnum.REVIEW,
            file_id=contract.id,
        )
        db.add(review_session)
        db.flush()
        job = ReviewJob(
            id="review-context-job", user_id=_user_id(headers), session_id=review_session.id,
            file_id=contract.id, status="completed", snapshot={
                "title": contract.title, "stance": "甲方", "intensity": "标准",
                "description": "核对付款", "contract_type": "信息化项目",
                "risk_points": [{
                    "id": 10, "task_id": 3, "session_id": review_session.id, "index": 2,
                    "original_content": "甲方应在验收合格后30日内付款。",
                    "risk_analysis": "原审阅认为付款期限不明确。", "risk_level": "中",
                    "suggested_content": "补充明确付款时间。", "risk_dim": "财务与付款",
                    "is_accepted": 0,
                }],
                "summary": {
                    "summary": "发现一项付款风险", "suggestion": "复核付款起算条件",
                    "overall_risk": "中", "review_status": "completed",
                    "review_scope": {"missing_materials": []},
                },
                "review_scope": {"missing_materials": []},
                "chunk_count": 1, "error": "",
            },
        )
        db.add(job)
        db.commit()
        return job.id


def test_review_chat_is_private_reused_and_receives_contract_and_review_context(
    client, auth_headers, tmp_path, monkeypatch,
):
    from app.services import chat_service

    review_id = _seed_completed_review(auth_headers, tmp_path)
    client.post("/api/users", json={"username": "review-chat-other", "password": "secret123"})
    other_login = client.post("/api/auth/login", json={
        "identifier": "review-chat-other", "password": "secret123",
    }).json()["data"]
    other_headers = {"Authorization": "Bearer " + other_login["access_token"]}
    assert client.post(
        f"/api/reviews/history/{review_id}/chat", headers=other_headers,
    ).status_code == 404

    created = client.post(f"/api/reviews/history/{review_id}/chat", headers=auth_headers)
    assert created.status_code == 200
    session = created.json()["data"]
    assert session["session_type"] == "chat"
    assert session["source_review_id"] == review_id
    repeated = client.post(f"/api/reviews/history/{review_id}/chat", headers=auth_headers)
    assert repeated.json()["data"]["session_id"] == session["session_id"]
    listed = client.get("/api/sessions?session_type=chat", headers=auth_headers).json()["data"]["items"]
    assert listed[0]["source_review_id"] == review_id

    calls = []

    class FakeClient:
        async def chat_stream_events(self, messages, **kwargs):
            calls.append(messages)
            yield "delta", "原审阅可能误读了明确的30日期限。"
            yield "usage", {"completion_tokens": 8}

    monkeypatch.setattr(chat_service, "get_sf_client", lambda: FakeClient())
    response = client.post("/api/chats", headers=auth_headers, json={
        "session_id": session["session_id"], "content": "第二项审阅意见是不是错了？",
    })
    assert response.status_code == 200
    system = calls[0][0]["content"]
    assert "甲方应在验收合格后30日内付款" in system
    assert "发现一项付款风险" in system
    assert "原审阅认为付款期限不明确" in system
    assert "明确指出原审阅哪里可能有误" in system
    history = client.get(
        f"/api/sessions/{session['session_id']}/history", headers=auth_headers,
    ).json()["data"]
    assert [item["role"] for item in history] == ["user", "assistant"]

    assert client.delete(f"/api/sessions/{session['session_id']}", headers=auth_headers).status_code == 200
    with SessionLocal() as db:
        assert db.get(ReviewChatContext, session["session_id"]) is None


def test_long_review_context_selects_the_explicitly_requested_risk(monkeypatch):
    from app.services import review_chat

    monkeypatch.setattr(review_chat.settings, "chat_review_context_max_chars", 4000)
    repeated = "具体分析和限定条件" * 400
    snapshot = {
        "review_id": "long", "summary": "summary", "review_scope": {},
        "risk_points": [
            {"index": 1, "risk_dim": "财务与付款", "risk_analysis": repeated},
            {"index": 2, "risk_dim": "验收交付与质保", "risk_analysis": repeated},
        ],
    }

    rendered = json.loads(review_chat.render_review_context(snapshot, "请解释第2项为什么这样判断"))
    assert rendered["risk_point_count"] == 2
    assert rendered["included_risk_point_count"] == 1
    assert rendered["risk_points"][0]["index"] == 2
