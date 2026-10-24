"""History selection must preserve facts and defer to full context when uncertain."""
from copy import deepcopy

import pytest

from app.services import chat_history


@pytest.fixture
def history(monkeypatch):
    monkeypatch.setattr(chat_history.settings, "chat_history_max_chars", 1400)
    monkeypatch.setattr(chat_history.settings, "chat_history_recent_messages", 2)
    return [
        {"role": "user", "content": "更正：甲方付款期限为验收后30日，金额100万元。"},
        {"role": "assistant", "content": "无关背景。\n\n付款期限为验收后30日。\n\n"
         "但应以验收完成并收到合规发票为前提。\n\n" + "交货安排的解释。" * 300},
        {"role": "user", "content": "双方已确认发票要求。"},
        {"role": "assistant", "content": "包装要求的解释。" * 300},
        {"role": "user", "content": "再解释一下验收程序。"},
        {"role": "assistant", "content": "验收应确认质量和数量。"},
    ]


def test_extracts_verbatim_conditions_and_preserves_all_user_facts(history):
    before = deepcopy(history)
    result = chat_history.select_history(history, "付款期限是多少？")
    assert len(str(result)) < len(str(history)) / 2
    assert [m for m in result if m["role"] == "user"] == [
        m for m in history if m["role"] == "user"
    ]
    assert result[-2:] == history[-2:]
    assert "付款期限为验收后30日。" in result[1]["content"]
    assert "但应以验收完成并收到合规发票为前提。" in result[1]["content"]
    assert history == before


@pytest.mark.parametrize("query", ["还有其他的风险吗", "请回顾全部历史", "刚才第二点怎么改",
                                   "这个风险怎么解决", "anything else?", "知识产权归谁？"])
def test_broad_ambiguous_or_unmatched_questions_use_full_history(history, query):
    assert chat_history.select_history(history, query) is history


def test_disabled_and_short_history_stay_complete(history, monkeypatch):
    monkeypatch.setattr(chat_history.settings, "chat_history_max_chars", 0)
    assert chat_history.select_history(history, "付款期限是多少") is history
    monkeypatch.setattr(chat_history.settings, "chat_history_max_chars", 100000)
    assert chat_history.select_history(history, "付款期限是多少") is history


def test_never_truncates_to_force_a_budget(history, monkeypatch):
    monkeypatch.setattr(chat_history.settings, "chat_history_max_chars", 10)
    assert chat_history.select_history(history, "付款期限是多少") is history


def test_single_paragraph_qualifications_remain_intact(history):
    history[1]["content"] = history[1]["content"].replace("\n\n", " ")
    assert chat_history.select_history(history, "付款期限是多少") is history


def test_api_selects_context_without_changing_stored_history(client, auth_headers,
                                                            monkeypatch, history):
    from app.core.db import SessionLocal
    from app.models.session_message import Message
    from app.services import chat_service

    sid = client.post("/api/sessions", json={"title": "history", "session_type": "chat"},
                      headers=auth_headers).json()["data"]["session_id"]
    with SessionLocal() as db:
        db.add_all([Message(session_id=sid, **message) for message in history])
        db.commit()
    calls = []

    class FakeClient:
        async def chat_stream_events(self, messages, **kwargs):
            calls.append(messages)
            yield "delta", "answer"

    monkeypatch.setattr(chat_service, "get_sf_client", FakeClient)
    response = client.post("/api/chats", json={"session_id": sid, "content": "付款期限是多少？"},
                           headers=auth_headers)
    assert response.status_code == 200
    assert sum(len(m["content"]) for m in calls[0][1:-1]) < 1400
    with SessionLocal() as db:
        rows = db.query(Message).filter_by(session_id=sid).order_by(Message.id).all()
        assert [{"role": row.role, "content": row.content} for row in rows[:6]] == history
        assert len(rows) == 8
