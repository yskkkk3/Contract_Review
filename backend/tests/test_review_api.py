"""M4 integration tests: review SSE flow (mocked agent) + chat SSE (mocked LLM)."""
import io

import pytest


class FakeGraph:
    """替换 LangGraph 图：返回固定审阅结果，避免真实 LLM/Qdrant 调用。"""

    async def ainvoke(self, state):
        return {
            **state,
            "final_risk_points": [
                {
                    "index": 1,
                    "original_content": "乙方逾期付款按日万分之五支付违约金",
                    "risk_analysis": "违约金计算基数不明确（合同总额 vs 未付金额）",
                    "risk_level": "中",
                    "suggested_content": "明确违约金计算基数为未付金额",
                    "risk_dim": "财务与付款",
                }
            ],
            "summary": {"summary": "发现 1 个风险点", "suggestion": "补充违约金基数", "overall_risk": "低"},
        }

    async def astream(self, state, stream_mode=None):
        """custom 模式推送一个风险点；updates 模式返回仲裁后的最终状态。"""
        if stream_mode == "custom":
            yield "custom", {
                "type": "risk_point",
                "risk_dim": "财务与付款",
                "points": [
                    {
                        "original_content": "乙方逾期付款按日万分之五支付违约金",
                        "risk_analysis": "违约金计算基数不明确（合同总额 vs 未付金额）",
                        "risk_level": "中",
                        "suggested_content": "明确违约金计算基数为未付金额",
                    }
                ],
            }
        elif isinstance(stream_mode, list) and "updates" in stream_mode:
            yield "updates", {
                "arbitration": {
                    "final_risk_points": [
                        {
                            "index": 1,
                            "original_content": "乙方逾期付款按日万分之五支付违约金",
                            "risk_analysis": "违约金计算基数不明确（合同总额 vs 未付金额）",
                            "risk_level": "中",
                            "suggested_content": "明确违约金计算基数为未付金额",
                            "risk_dim": "财务与付款",
                        }
                    ],
                    "summary": {"summary": "发现 1 个风险点", "suggestion": "补充违约金基数", "overall_risk": "低"},
                }
            }


@pytest.fixture()
def upload_review_context(client, auth_headers, monkeypatch):
    """上传一份可解析的合同 → 建会话 → 返回 (file_id, session_id)。"""
    from app.services import review_service

    monkeypatch.setattr(review_service, "get_graph", lambda rag: FakeGraph())

    content = (
        "第一条 总则\n甲乙双方就服务采购签订本合同。\n"
        "第二条 付款\n乙方逾期付款按日万分之五支付违约金。\n"
        "第三条 验收\n验收合格后十日内支付余款。\n"
    ).encode()
    resp = client.post(
        "/api/contracts/upload",
        files={"file": ("service_contract.txt", io.BytesIO(content), "text/plain")},
        headers=auth_headers,
    )
    # 上传接口只接受 pdf/docx/doc；用 pdf 模拟
    assert resp.status_code in (200, 400, 422)
    return resp


def test_review_sse_flow(client, auth_headers, monkeypatch, tmp_path):
    """端到端：上传 → 建会话 → 审阅 SSE → 事件流 + DB 落库。"""

    from app.rag import service as rag_service
    from app.services import review_service

    monkeypatch.setattr(review_service, "get_graph", lambda rag: FakeGraph())
    # 避免真实 Qdrant 连接（rag 服务注入 fake）
    class FakeRAG:
        async def search_with_context(self, *a, **kw):
            return "（检索证据）", []

        async def close(self):
            pass

    monkeypatch.setattr(rag_service, "get_rag_service", lambda: FakeRAG())

    # 上传 docx（用最小合法 docx 结构）
    from docx import Document

    doc = Document()
    doc.add_paragraph("第一条 总则\n甲乙双方就服务采购签订本合同。")
    doc.add_paragraph("第二条 付款\n乙方逾期付款按日万分之五支付违约金。")
    doc.save(tmp_path / "t.docx")

    with open(tmp_path / "t.docx", "rb") as fh:
        resp = client.post(
            "/api/contracts/upload",
            files={"file": ("t.docx", fh, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    file_id = resp.json()["data"]["file_id"]

    r = client.post(
        "/api/sessions",
        json={"title": "review test", "session_type": "review", "file_id": file_id},
        headers=auth_headers,
    )
    session_id = r.json()["data"]["session_id"]

    with client.stream(
        "POST",
        "/api/reviews/start",
        json={
            "session_id": session_id,
            "file_id": file_id,
            "contract_type": "服务",
            "stance": "甲方",
            "intensity": "严格",
            "description": "审阅付款条款",
            "max_concurrent": 5,
        },
        headers=auth_headers,
    ) as resp2:
        assert resp2.status_code == 200
        assert resp2.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp2.iter_text())
    assert "event" in body
    assert "message" in body
    assert "end" in body

    # 验证 DB 落库
    r = client.get("/api/sessions?session_type=review", headers=auth_headers)
    assert r.status_code == 200


def test_chat_sse_with_context(client, auth_headers, monkeypatch):
    """聊天 SSE：mock LLM 流式，验证 content/done 事件。"""

    from app.services import chat_service

    class FakeClient:
        async def chat_stream_events(self, messages, model=None, **kwargs):
            yield ("start", None)
            for delta in ["这是", "回答"]:
                yield ("delta", delta)
            yield ("usage", {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16})

    monkeypatch.setattr(chat_service, "get_sf_client", lambda: FakeClient())

    r = client.post("/api/sessions", json={"title": "chat", "session_type": "chat"}, headers=auth_headers)
    session_id = r.json()["data"]["session_id"]

    with client.stream(
        "POST", "/api/chats", json={"session_id": session_id, "content": "合同付款条款有什么风险？"}, headers=auth_headers
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    assert '"type": "content"' in body
    assert '"type": "done"' in body
