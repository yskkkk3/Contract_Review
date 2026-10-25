"""Chat timing and stream lifecycle regression tests, without network calls."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.core import metrics


def events(response):
    return [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]


def session_id(client, auth_headers):
    return client.post("/api/sessions", json={"title": "timing", "session_type": "chat"},
                       headers=auth_headers).json()["data"]["session_id"]


def test_ttft_includes_contract_history_and_persistence(client, auth_headers, monkeypatch):
    from app.services import chat_service

    clock = [0.0]
    monkeypatch.setattr(chat_service.time, "monotonic", lambda: clock[0])

    def load(*args):
        clock[0] += 0.2
        return "contract"

    async def history(*args):
        clock[0] += 0.3
        return []

    async def stream(*args, **kwargs):
        clock[0] += 0.1
        yield "delta", "answer"
        clock[0] += 0.4
        yield "usage", {"completion_tokens": 5}

    monkeypatch.setattr(chat_service, "_load_contract_text", load)
    monkeypatch.setattr(chat_service, "_history_messages", history)
    monkeypatch.setattr(chat_service, "get_sf_client", lambda: SimpleNamespace(chat_stream_events=stream))
    response = client.post("/api/chats", json={"session_id": session_id(client, auth_headers),
                                             "content": "question"}, headers=auth_headers)
    result = events(response)[-1]["metrics"]
    assert result["ttft_ms"] == 600
    assert result["total_ms"] == 1000
    assert result["phases_ms"]["contract_load_ms"] == 200
    assert result["phases_ms"]["history_load_ms"] == 300
    assert result["phases_ms"]["model_first_content_ms"] == 100
    assert result["phases_ms"]["generation_ms"] == 400
    assert metrics.snapshot()["chat"]["statuses"]["success"] >= 1


async def test_idle_timeout_sends_heartbeats_and_closes_source(monkeypatch):
    from app.services import chat_service

    monkeypatch.setattr(chat_service.settings, "chat_stream_timeout", 0.03)
    monkeypatch.setattr(chat_service.settings, "chat_heartbeat_interval", 0.005)
    closed, received = [], []

    async def stream(*args, **kwargs):
        try:
            yield "start", None
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    with pytest.raises(chat_service.ChatStreamTimeout):
        async for event in chat_service._stream_events(SimpleNamespace(chat_stream_events=stream), []):
            received.append(event)
    assert ("heartbeat", None) in received
    assert closed == [True]


async def test_reasoning_activity_does_not_bypass_first_content_deadline(monkeypatch):
    from app.services import chat_service

    monkeypatch.setattr(chat_service.settings, "chat_first_content_timeout", 0.03)
    monkeypatch.setattr(chat_service.settings, "chat_stream_timeout", 1)
    closed = []

    async def stream(*args, **kwargs):
        try:
            while True:
                yield "activity", None
                await asyncio.sleep(0.001)
        finally:
            closed.append(True)

    async def consume():
        return [e async for e in chat_service._stream_events(SimpleNamespace(chat_stream_events=stream), [])]

    with pytest.raises(chat_service.ChatStreamTimeout):
        await asyncio.wait_for(consume(), 1)
    assert closed == [True]


async def test_slow_downstream_is_not_misclassified_as_upstream_idle(monkeypatch):
    from app.services import chat_service

    monkeypatch.setattr(chat_service.settings, "chat_stream_timeout", 0.02)

    async def stream(*args, **kwargs):
        yield "delta", "first"
        yield "delta", "second"

    source = chat_service._stream_events(SimpleNamespace(chat_stream_events=stream), [])
    assert await anext(source) == ("delta", "first")
    await asyncio.sleep(0.03)  # downstream rendering/backpressure, not an upstream wait
    assert await anext(source) == ("delta", "second")
    await source.aclose()


def test_failed_partial_answer_is_explicit_and_not_persisted(client, auth_headers, monkeypatch):
    from app.core.db import SessionLocal
    from app.models.session_message import Message
    from app.services import chat_service

    async def stream(*args, **kwargs):
        yield "delta", "partial answer"
        raise RuntimeError("internal provider details must not reach browser")

    monkeypatch.setattr(chat_service, "get_sf_client", lambda: SimpleNamespace(chat_stream_events=stream))
    sid = session_id(client, auth_headers)
    response = client.post("/api/chats", json={"session_id": sid, "content": "question"},
                           headers=auth_headers)
    received = events(response)
    assert received[0]["type"] == "start"
    assert received[-1]["type"] == "error"
    assert received[-1]["partial"] is True
    assert not any(e["type"] == "done" for e in received)
    assert "internal provider" not in response.text
    assert response.headers["x-accel-buffering"] == "no"
    with SessionLocal() as db:
        assert db.query(Message).filter_by(session_id=sid, role="assistant").count() == 0


async def test_closing_response_closes_model_generator_and_records_cancellation(monkeypatch):
    from app.services import chat_service

    closed = []

    async def stream(*args, **kwargs):
        try:
            yield "delta", "partial"
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    async def history(*args):
        return []

    monkeypatch.setattr(chat_service, "get_sf_client", lambda: SimpleNamespace(chat_stream_events=stream))
    monkeypatch.setattr(chat_service, "_load_contract_text", lambda *args: "")
    monkeypatch.setattr(chat_service, "_history_messages", history)
    db = SimpleNamespace(add=lambda *args: None, commit=lambda: None)
    response = await chat_service.stream_chat(SimpleNamespace(content="question", parent_id=None),
                                              SimpleNamespace(id=1, file_id=None), None, db)
    body = response.body_iterator
    await anext(body)  # start, before waiting for the model
    assert "partial" in await anext(body)
    await body.aclose()
    assert closed == [True]
    assert metrics.snapshot()["chat"]["statuses"]["cancelled"] >= 1


def test_idle_timeout_is_an_error_event_without_a_done_event(client, auth_headers, monkeypatch):
    from app.services import chat_service

    monkeypatch.setattr(chat_service.settings, "chat_stream_timeout", 0.02)
    monkeypatch.setattr(chat_service.settings, "chat_heartbeat_interval", 0.005)

    async def stream(*args, **kwargs):
        yield "start", None
        await asyncio.Event().wait()

    monkeypatch.setattr(chat_service, "get_sf_client", lambda: SimpleNamespace(chat_stream_events=stream))
    response = client.post("/api/chats", json={"session_id": session_id(client, auth_headers),
                                             "content": "question"}, headers=auth_headers)
    assert events(response)[-1]["code"] == "timeout"
    assert not any(e["type"] == "done" for e in events(response))
    assert metrics.snapshot()["chat"]["statuses"]["timeout"] >= 1
