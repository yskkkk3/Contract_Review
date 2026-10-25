"""Discover configured MCP tools and open a fresh, bounded session per invocation."""
import asyncio
import hashlib
import json
import logging
import re
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.langfuse import traced
from app.core.runtime_config import environment_value

logger = logging.getLogger(__name__)


class MCPClientManager:
    def __init__(self):
        self._tools = []

    @asynccontextmanager
    async def _session(self, url):
        import httpx
        from mcp import ClientSession
        from mcp.client.sse import sse_client
        from mcp.client.streamable_http import streamable_http_client

        settings = get_settings()
        headers = json.loads(environment_value(settings.mcp_headers_env) or "{}") if settings.mcp_headers_env else {}
        if not isinstance(headers, dict) or not all(isinstance(v, str) for v in headers.values()):
            raise ValueError("MCP headers must be a JSON object of strings")
        if urlsplit(url).path.rstrip("/").endswith("/sse"):
            async with sse_client(url, headers=headers) as streams, ClientSession(*streams) as session:
                await session.initialize()
                yield session
        else:
            async with (
                httpx.AsyncClient(headers=headers, timeout=settings.mcp_tool_timeout) as http,
                streamable_http_client(url, http_client=http) as streams,
                ClientSession(streams[0], streams[1]) as session,
            ):
                await session.initialize()
                yield session

    async def connect_all(self):
        from mcp.types import PaginatedRequestParams

        self._tools.clear()
        settings = get_settings()
        if not settings.mcp_enabled:
            return
        for url in dict.fromkeys(u.strip() for u in settings.mcp_server_urls.split(",") if u.strip()):
            parsed = urlsplit(url)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query:
                logger.warning("Skipping invalid MCP endpoint")
                continue
            try:
                tools = []
                async with asyncio.timeout(settings.mcp_tool_timeout), self._session(url) as session:
                    cursor = None
                    seen = set()
                    while True:
                        result = await session.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
                        tools.extend(result.tools)
                        cursor = result.next_cursor
                        if not cursor:
                            break
                        if cursor in seen:
                            raise ValueError("Repeated MCP discovery cursor")
                        seen.add(cursor)
                for tool in tools:
                    if tool.input_schema.get("type") == "object":
                        self._tools.append((url, tool))
                logger.info("MCP discovery complete: %d tools", len(tools))
            except Exception:
                # Local review tools remain available when an optional external server fails.
                logger.warning("MCP discovery failed for host=%s", parsed.hostname, exc_info=True)

    @traced("mcp.call_tool", as_type="tool")
    async def call_tool(self, server_url, tool_name, arguments):
        settings = get_settings()
        if not settings.mcp_enabled:
            raise RuntimeError("MCP is disabled")
        if not any(url == server_url and tool.name == tool_name for url, tool in self._tools):
            raise ValueError("MCP tool was not discovered")
        async with asyncio.timeout(settings.mcp_tool_timeout), self._session(server_url) as session:
            result = await session.call_tool(tool_name, arguments)
            if result.is_error:
                raise RuntimeError("MCP tool returned an error")
            return json.dumps([part.model_dump(mode="json") for part in result.content], ensure_ascii=False)

    def agent_tools(self):
        from app.agent.tools.registry import Tool

        if not get_settings().mcp_enabled:
            return []
        tools = []
        for url, remote in self._tools:
            def make_handler(endpoint, name):
                async def handler(arguments, _context):
                    return await self.call_tool(endpoint, name, arguments), []
                return handler
            digest = hashlib.sha256((url + "\n" + remote.name).encode()).hexdigest()[:10]
            name = re.sub(r"[^a-zA-Z0-9_-]", "_", remote.name)[:40]
            tools.append(Tool(
                name=f"mcp_{digest}_{name}", description=remote.description or remote.name,
                parameters=remote.input_schema, handler=make_handler(url, remote.name),
            ))
        return tools

    async def close_all(self):
        self._tools.clear()


mcp_client_manager = MCPClientManager()
