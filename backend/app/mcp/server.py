"""MCP Server：把本系统能力暴露为标准 MCP Tools（stdio / SSE 双传输）。

启动：uv run python -m app.mcp.server            # stdio 模式
挂载：app 内 /api/mcp/sse 提供 SSE transport（见 main.py）
"""
import json

from app.core.config import get_settings
from app.rag.client import get_sf_client
from app.rag.service import get_rag_service
from app.services.chat_service import SYSTEM_TEMPLATE

settings = get_settings()


def _build_server():
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("contract-review", instructions="高校合同智能审阅 Agent 的 MCP 工具集")

    @mcp.tool()
    async def search_knowledge_base(query: str, risk_dim: str = "") -> str:
        """检索合同审阅知识库（深大制度/法规/模板），返回 Top-3 证据文本。risk_dim 可选：主体资格与合规/财务与付款/知识产权与保密/违约责任与解除/验收交付与质保/争议解决与管辖。"""
        rag = get_rag_service()
        await rag.ensure_ready()
        ev = await rag.search(query, risk_dim=risk_dim or None, top_k=3)
        return json.dumps(
            [{"doc_id": e.chunk.doc_id, "section": e.chunk.section, "text": e.chunk.text[:300], "score": round(e.score, 4)} for e in ev],
            ensure_ascii=False,
        )

    @mcp.tool()
    async def ask_contract_assistant(question: str, contract_context: str = "") -> str:
        """围绕合同文本提问，返回 LLM 答案（无流式，供 MCP 客户端使用）。"""
        sf = get_sf_client()
        messages = [
            {"role": "system", "content": SYSTEM_TEMPLATE + (f"\n【合同原文】\n{contract_context[:8000]}" if contract_context else "")},
            {"role": "user", "content": question},
        ]
        resp = await sf.chat(messages, model=settings.llm_chat_model, temperature=0.2, max_tokens=1024)
        return resp

    @mcp.tool()
    async def health_check() -> str:
        """返回系统运行状态与模型配置概要。"""
        return json.dumps(
            {"app": settings.app_name, "review_model": settings.llm_review_model,
             "chat_model": settings.llm_chat_model, "embedding": settings.embedding_model},
            ensure_ascii=False,
        )

    return mcp


def run_stdio() -> None:
    """stdio 传输：供 Claude/Cursor 等 MCP 客户端通过命令启动。"""
    _build_server().run(transport="stdio")


def get_fastmcp_app():
    """SSE 传输：挂载到 FastAPI（/api/mcp/sse）。"""
    return _build_server().streamable_http_app()


if __name__ == "__main__":
    run_stdio()
