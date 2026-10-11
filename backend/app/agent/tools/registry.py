"""Agent 工具注册表：JSON Schema 驱动的 Function Calling 工具定义。

简历点：工具与 schema 分离——模型只见 schema（name/description/parameters），
执行由注册的 async handler 完成；确定性工具（calc_penalty）与语义工具
（search_regulations / get_clause / lookup_template）边界清晰。
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

# 工具执行的运行时上下文：由调用方注入（rag 服务 / 合同文件等）
ToolContext = dict[str, Any]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema（OpenAI function calling 要求）
    handler: Callable[[dict, ToolContext], Awaitable[tuple[str, list[str]]]]

    @property
    def schema(self) -> dict:
        """OpenAI 工具 schema：description 必填，parameters 为 JSON Schema object。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ---------- 确定性工具：违约金计算（LLM 不做数学） ----------
_PENALTY_PARAMS: dict = {
    "type": "object",
    "properties": {
        "amount": {"type": "number", "description": "合同金额（元）"},
        "rate": {"type": "number", "description": "日违约金比例（小数，如 0.0005 = 日万分之五）"},
        "days": {"type": "integer", "description": "逾期天数"},
    },
    "required": ["amount", "rate", "days"],
    "additionalProperties": False,
}


async def _calc_penalty(args: dict, ctx: ToolContext) -> tuple[str, list[str]]:
    amount = float(args.get("amount", 0))
    rate = float(args.get("rate", 0))
    days = int(args.get("days", 0))
    penalty = round(amount * rate * days, 2)
    return f"违约金 = {amount} × {rate} × {days} = {penalty} 元", []


# ---------- 语义工具：知识库检索 / 条款定位 / 模板查询 ----------
async def _search_regulations(args: dict, ctx: ToolContext) -> tuple[str, list[str]]:
    rag = ctx.get("rag")
    if rag is None:
        return "（检索服务不可用）", []
    query = str(args.get("query", ""))
    risk_dim = args.get("risk_dim")
    top_k = int(args.get("top_k", 3))
    from app.rag.service import RAGService

    if not isinstance(rag, RAGService):
        return "（检索服务不可用）", []
    context, evidence = await rag.search_with_context(query, risk_dim=risk_dim, top_k=top_k)
    doc_ids = list({e.chunk.doc_id for e in evidence})
    return context, doc_ids


async def _get_clause(args: dict, ctx: ToolContext) -> tuple[str, list[str]]:
    content = ctx.get("contract_content") or ""
    index = int(args.get("clause_index", 0))
    clauses = ctx.get("clauses") or []
    if clauses and 0 <= index < len(clauses):
        return clauses[index][:2000], []
    if content:
        return content[:2000], []
    return "（未找到该条款）", []


async def _lookup_template(args: dict, ctx: ToolContext) -> tuple[str, list[str]]:
    rag = ctx.get("rag")
    if rag is None:
        return "（模板库不可用）", []
    query = f"{args.get('contract_type', '')} 合同模板"
    context, evidence = await rag.search_with_context(query, risk_dim=None, top_k=2)
    doc_ids = list({e.chunk.doc_id for e in evidence})
    return context, doc_ids


_SEARCH_PARAMS: dict = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "检索关键词（法规/制度/模板）"},
        "risk_dim": {
            "type": "string",
            "description": "风险维度：主体资格与合规 / 财务与付款 / 知识产权与保密 / 违约责任与解除 / 验收交付与质保 / 争议解决与管辖",
        },
        "top_k": {"type": "integer", "description": "返回证据条数，默认 3"},
    },
    "required": ["query"],
    "additionalProperties": False,
}

_CLAUSE_PARAMS: dict = {
    "type": "object",
    "properties": {
        "clause_index": {"type": "integer", "description": "条款索引（从 0 开始）"},
    },
    "required": ["clause_index"],
    "additionalProperties": False,
}

_TEMPLATE_PARAMS: dict = {
    "type": "object",
    "properties": {
        "contract_type": {"type": "string", "description": "合同类型，如 服务采购 / 货物采购 / 工程"},
    },
    "required": ["contract_type"],
    "additionalProperties": False,
}


def default_tools() -> list[Tool]:
    """默认工具集：Agent 审阅时可调用的全部工具。"""
    return [
        Tool(
            name="search_regulations",
            description="检索高校采购相关法规、校内制度与合同模板知识库，返回带来源标注的证据文本，用于支撑审阅判断",
            parameters=_SEARCH_PARAMS,
            handler=_search_regulations,
        ),
        Tool(
            name="get_clause",
            description="获取合同中指定条款的原文，用于精确定位证据、防止引用幻觉",
            parameters=_CLAUSE_PARAMS,
            handler=_get_clause,
        ),
        Tool(
            name="calc_penalty",
            description="计算逾期付款违约金金额（确定性计算，LLM 不应自行心算）",
            parameters=_PENALTY_PARAMS,
            handler=_calc_penalty,
        ),
        Tool(
            name="lookup_template",
            description="按合同类型查询模板库，用于修改建议与条款比对",
            parameters=_TEMPLATE_PARAMS,
            handler=_lookup_template,
        ),
    ]


def tool_schemas(tools: list[Tool]) -> list[dict]:
    return [t.schema for t in tools]
