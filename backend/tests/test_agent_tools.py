"""Tool Calling 单元测试：schema 合法性 / 确定性工具 / 执行器循环 / 降级与截断。"""
from __future__ import annotations

import types

from app.agent.tools.executor import call_llm_with_tools
from app.agent.tools.registry import Tool, default_tools, tool_schemas
from app.core.config import get_settings


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.function = types.SimpleNamespace(name=name, arguments=arguments)


class FakeMessage:
    def __init__(self, content: str | None = None, tool_calls: list | None = None):
        self.content = content
        self.tool_calls = tool_calls


class ScriptedClient:
    """按脚本返回结果的假 LLM 客户端。"""

    def __init__(self, responses: list[FakeMessage]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def chat_with_tools(self, messages, tools, model=None, **kwargs):
        self.calls.append({"messages": list(messages), "tools": tools})
        return self.responses.pop(0)

    async def chat(self, messages, model=None, **kwargs):
        return "chat fallback"


# ---------- schema 合法性 ----------
def test_tool_schemas_valid():
    schemas = tool_schemas(default_tools())
    names = {s["function"]["name"] for s in schemas}
    assert names == {"search_regulations", "get_clause", "calc_penalty", "lookup_template"}
    for s in schemas:
        fn = s["function"]
        assert fn["description"], f"{fn['name']} description 必填（OpenAI 要求）"
        assert fn["parameters"]["type"] == "object"
        assert "properties" in fn["parameters"]
        assert fn["parameters"]["additionalProperties"] is False  # strict schema


# ---------- 确定性工具 ----------
async def test_calc_penalty_deterministic():
    tools = {t.name: t for t in default_tools()}
    text, doc_ids = await tools["calc_penalty"].handler(
        {"amount": 100000, "rate": 0.0005, "days": 30}, {}
    )
    assert "1500.0" in text  # 100000 × 0.0005 × 30
    assert doc_ids == []


# ---------- 执行器：单轮工具调用 ----------
async def test_executor_single_tool_round():
    client = ScriptedClient(
        [
            FakeMessage(
                tool_calls=[FakeToolCall("call_1", "calc_penalty", '{"amount": 200000, "rate": 0.001, "days": 10}')]
            ),
            FakeMessage(content="{\"risk_points\": [{\"original_content\": \"x\", \"risk_analysis\": \"y\", \"risk_level\": \"高\", \"suggested_content\": \"z\"}]}"),
        ]
    )
    text, records = await call_llm_with_tools(
        client,
        [{"role": "user", "content": "审阅"}],
        default_tools(),
        model="test-model",
        context={"rag": None},
    )
    assert "risk_points" in text
    assert len(records) == 1
    assert records[0].name == "calc_penalty"
    assert records[0].ok is True
    # 工具消息已回喂模型
    assert client.calls[1]["messages"][-1]["role"] == "tool"
    assert client.calls[1]["messages"][-1]["tool_call_id"] == "call_1"


# ---------- 执行器：迭代上限防死循环 ----------
async def test_executor_max_iterations():
    client = ScriptedClient(
        [FakeMessage(tool_calls=[FakeToolCall(f"c{i}", "calc_penalty", '{"amount": 1, "rate": 1, "days": 1}')]) for i in range(5)]
    )
    text, records = await call_llm_with_tools(
        client, [{"role": "user", "content": "x"}], default_tools(), model="m", max_iterations=3
    )
    assert len(records) == 3  # 到上限终止，不无限循环
    assert len(client.calls) == 3


# ---------- 总开关关闭：跳过工具循环 ----------
async def test_executor_disabled_fallback(monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_tool_calling_enabled", False)
    client = ScriptedClient([])
    text, records = await call_llm_with_tools(
        client, [{"role": "user", "content": "x"}], default_tools(), model="m"
    )
    assert text == "chat fallback"
    assert records == []
    assert client.calls == []  # 未走 chat_with_tools


# ---------- 工具异常回喂模型 ----------
async def test_tool_error_fed_back():
    def boom(args, ctx):
        raise RuntimeError("boom")

    bad_tool = Tool(
        name="bad_tool", description="d", parameters={"type": "object", "properties": {}}, handler=boom
    )
    client = ScriptedClient(
        [
            FakeMessage(tool_calls=[FakeToolCall("c1", "bad_tool", "{}")]),
            FakeMessage(content="ok"),
        ]
    )
    text, records = await call_llm_with_tools(client, [], [bad_tool], model="m")
    assert text == "ok"
    assert records[0].ok is False
    assert "工具执行失败" in client.calls[1]["messages"][-1]["content"]


async def test_tool_billing_failure_stops_before_another_model_round():
    import httpx
    import pytest

    async def unavailable(args, ctx):
        response = httpx.Response(400, json={"code": "Arrearage"},
                                  request=httpx.Request("POST", "https://example.org/reranks"))
        raise httpx.HTTPStatusError("billing unavailable", request=response.request, response=response)

    tool = Tool(name="billing_tool", description="test", parameters={"type": "object", "properties": {}}, handler=unavailable)
    client = ScriptedClient([FakeMessage(tool_calls=[FakeToolCall("c1", "billing_tool", "{}")])])
    with pytest.raises(httpx.HTTPStatusError):
        await call_llm_with_tools(client, [], [tool], model="m")
    assert len(client.calls) == 1


# ---------- 结果截断 ----------
async def test_tool_result_truncation(monkeypatch):
    monkeypatch.setattr(get_settings(), "tool_result_max_chars", 50)

    def long_handler(args, ctx):
        return "x" * 200, []

    long_tool = Tool(
        name="long_tool",
        description="d",
        parameters={"type": "object", "properties": {}},
        handler=long_handler,
    )
    client = ScriptedClient(
        [
            FakeMessage(tool_calls=[FakeToolCall("c1", "long_tool", "{}")]),
            FakeMessage(content="done"),
        ]
    )
    _, records = await call_llm_with_tools(client, [], [long_tool], model="m")
    fed = client.calls[1]["messages"][-1]["content"]
    assert len(fed) <= 60
    assert "已截断" in fed


async def test_specialist_keeps_only_explicit_retrieved_citations(monkeypatch):
    import asyncio

    from app.agent.nodes import specialist
    from app.agent.tools.executor import ToolCallRecord

    async def run_tools(*args, **kwargs):
        return (
            '{"risk_points": [{"original_content": "付款条件不明", "risk_analysis": "存在付款争议", '
            '"risk_level": "中", "suggested_content": "明确起算日", '
            '"evidence_refs": ["支持文档", "伪造文档", "支持文档", {}]}]}',
            [ToolCallRecord("search_regulations", {}, ["支持文档", "其他命中"], True, 1)],
        )

    monkeypatch.setattr(specialist, "get_sf_client", lambda: object())
    monkeypatch.setattr(specialist, "call_llm_with_tools", run_tools)
    state = {"stance": "甲方", "intensity": "标准", "chunks": ["付款条件不明"]}
    result = await specialist._run_specialist(
        asyncio.Semaphore(1), state["chunks"][0], "财务与付款", state, None,
    )
    assert result["result"][0]["evidence_refs"] == ["支持文档"]
