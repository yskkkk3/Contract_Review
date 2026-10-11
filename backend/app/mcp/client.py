"""MCP Client：连接外部 MCP Server 并暴露统一调用入口。

配置：MCP_SERVER_URLS=url1,url2（SSE/streamable-http）；MCP_ENABLED=true 时启用。
"""
import json
import logging

from app.core.config import get_settings

logger = logging.getLogger("mcp.client")


class MCPClientManager:
    """管理多个外部 MCP server 连接（懒加载）。"""

    def __init__(self):
        self._sessions = {}

    async def connect_all(self) -> None:
        s = get_settings()
        if not s.mcp_enabled or not s.mcp_server_urls:
            return
        try:
            from mcp.client.sse import sse_client
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp client deps unavailable: %s", exc)
            return
        for url in [u.strip() for u in s.mcp_server_urls.split(",") if u.strip()]:
            try:
                ctx = sse_client(url)
                self._sessions[url] = ctx
                logger.info("MCP server connected: %s", url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("MCP connect failed %s: %s", url, exc)

    async def call_tool(self, server_url: str, tool_name: str, arguments: dict) -> str:
        s = get_settings()
        if not s.mcp_enabled:
            return "MCP disabled (MCP_ENABLED=false)"
        from mcp import ClientSession

        ctx = self._sessions.get(server_url)
        if ctx is None:
            return f"MCP server not connected: {server_url}"
        async with ctx as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return json.dumps([{"type": c.type, "text": c.text} for c in result.content], ensure_ascii=False)

    async def close_all(self) -> None:
        self._sessions.clear()


mcp_client_manager = MCPClientManager()
