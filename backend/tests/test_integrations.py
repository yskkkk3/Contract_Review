"""Observability and MCP exercise real SDK shapes without external services."""
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace

import pytest


def test_langfuse_configuration_and_failure_isolation(monkeypatch):
    import langfuse

    from app.core import langfuse as module

    events = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["tracing_enabled"] is True
            assert "enabled" not in kwargs

        @contextmanager
        def start_as_current_observation(self, **kwargs):
            events.append(("start", kwargs))
            try:
                yield SimpleNamespace(update=lambda **values: events.append(("update", values)))
            finally:
                events.append(("end", None))

        def flush(self):
            events.append(("flush", None))

        def shutdown(self):
            events.append(("shutdown", None))

    @contextmanager
    def attributes(**kwargs):
        events.append(("attributes", kwargs))
        yield

    settings = module.get_settings()
    monkeypatch.setattr(settings, "langfuse_public_key", "test-public")
    monkeypatch.setattr(settings, "langfuse_secret_key", "test-private")
    monkeypatch.setattr(module, "_lf", None)
    monkeypatch.setattr(langfuse, "Langfuse", Client)
    monkeypatch.setattr(langfuse, "propagate_attributes", attributes)
    with pytest.raises(ValueError, match="business failure"), module.observation("chat", session_id=12):
        raise ValueError("business failure")
    assert ("attributes", {"session_id": "12"}) in events
    assert any(kind == "update" and values["level"] == "ERROR" for kind, values in events)
    module.shutdown_langfuse()
    assert [kind for kind, _ in events][-2:] == ["flush", "shutdown"]


async def test_tracing_outage_does_not_change_business_result(monkeypatch):
    from app.core import langfuse as module

    def fail(**kwargs):
        raise RuntimeError("telemetry offline")

    monkeypatch.setattr(module, "get_langfuse", lambda: SimpleNamespace(start_as_current_observation=fail))

    @module.traced("rag.search")
    async def operation():
        return ["evidence"]

    assert await operation() == ["evidence"]


async def test_mcp_discovery_executes_through_agent_tools_repeatedly(monkeypatch):
    from mcp.types import TextContent, Tool

    from app.agent.tools.executor import _run_tool
    from app.agent.tools.registry import default_tools
    from app.mcp import client as module

    manager = module.MCPClientManager()
    settings = module.get_settings()
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_server_urls", "https://one.example/mcp,https://two.example/sse")
    monkeypatch.setattr(module, "mcp_client_manager", manager)
    sessions = []

    class Session:
        async def list_tools(self, params=None):
            return SimpleNamespace(tools=[Tool(name="lookup", description="lookup", inputSchema={
                "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"],
            })], next_cursor=None)

        async def call_tool(self, name, arguments):
            return SimpleNamespace(is_error=False, content=[TextContent(type="text", text=arguments["query"])])

    @asynccontextmanager
    async def session(url):
        sessions.append(url)
        yield Session()

    monkeypatch.setattr(manager, "_session", session)
    await manager.connect_all()
    tools = default_tools()
    remote = [tool for tool in tools if tool.name.startswith("mcp_")]
    assert len(remote) == 2 and remote[0].name != remote[1].name
    call = SimpleNamespace(function=SimpleNamespace(name=remote[0].name, arguments='{"query":"test"}'))
    for _ in range(2):
        result, record = await _run_tool(call, {t.name: t for t in tools}, {})
        assert "test" in result and record.ok
        assert record.doc_ids == []  # External text is not falsely treated as verified legal evidence.
    assert len(sessions) == 4
    await manager.close_all()
    assert manager.agent_tools() == []


async def test_mcp_server_uses_correct_path_and_lifespan():
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    from app.mcp.server import get_fastmcp_app, get_mcp_server

    app = get_fastmcp_app()
    assert "/" in [route.path for route in app.routes]
    async with (
        get_mcp_server().session_manager.run(),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8080") as http,
        streamable_http_client("http://127.0.0.1:8080/", http_client=http) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        await session.initialize()
        result = await session.call_tool("health_check", {})
        assert not result.is_error
        assert "review_model" in result.content[0].text


async def test_mcp_disabled_exposes_no_external_tools(monkeypatch):
    from app.mcp import client as module

    monkeypatch.setattr(module.get_settings(), "mcp_enabled", False)
    manager = module.MCPClientManager()
    await manager.connect_all()
    assert manager.agent_tools() == []
    with pytest.raises(RuntimeError, match="disabled"):
        await manager.call_tool("http://localhost/mcp", "anything", {})
