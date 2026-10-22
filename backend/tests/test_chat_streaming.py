"""Chat timing and stream lifecycle regression tests, without network calls."""
import json
from types import SimpleNamespace

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
