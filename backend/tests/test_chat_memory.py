"""Chat memory integration tests."""


def test_chat_uses_complete_history_from_current_session(client, auth_headers, monkeypatch):
    """模型应收到当前会话全部历史，且不能混入其他会话消息。"""
    from app.services import chat_service

    calls: list[list[dict]] = []

    class FakeClient:
        async def chat_stream_events(self, messages, model=None, **kwargs):
            calls.append(messages)
            yield ("delta", "已记录")
            yield ("usage", {"completion_tokens": 2})

    monkeypatch.setattr(chat_service, "get_sf_client", lambda: FakeClient())

    first = client.post(
        "/api/sessions",
        json={"title": "完整记忆", "session_type": "chat"},
        headers=auth_headers,
    )
    first_session_id = first.json()["data"]["session_id"]

    second = client.post(
        "/api/sessions",
        json={"title": "隔离会话", "session_type": "chat"},
        headers=auth_headers,
    )
    second_session_id = second.json()["data"]["session_id"]

    # 11 轮会产生 22 条历史消息，超过旧实现的 20 条上限。
    for index in range(11):
        response = client.post(
            "/api/chats",
            json={"session_id": first_session_id, "content": f"第{index + 1}轮问题"},
            headers=auth_headers,
        )
        assert response.status_code == 200

    other_response = client.post(
        "/api/chats",
        json={"session_id": second_session_id, "content": "其他会话的私有内容"},
        headers=auth_headers,
    )
    assert other_response.status_code == 200

    final_response = client.post(
        "/api/chats",
        json={"session_id": first_session_id, "content": "请回顾全部历史"},
        headers=auth_headers,
    )
    assert final_response.status_code == 200

    final_messages = calls[-1]
    conversation = final_messages[1:]
    assert len(conversation) == 23
    assert conversation[0] == {"role": "user", "content": "第1轮问题"}
    assert conversation[1] == {"role": "assistant", "content": "已记录"}
    assert conversation[-2] == {"role": "assistant", "content": "已记录"}
    assert conversation[-1] == {"role": "user", "content": "请回顾全部历史"}
    assert all(message["content"] != "其他会话的私有内容" for message in conversation)
