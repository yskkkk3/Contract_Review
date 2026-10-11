"""Agent 工具执行器：OpenAI Tool Calling 循环（并行执行 + 失败回喂 + 防死循环）。

流程：
  1. chat.completions.create(tools=[...], tool_choice="auto")
  2. 返回 tool_calls → asyncio.gather 并行执行 handler → 追加 role="tool" 消息 → 再调 LLM
  3. 无 tool_calls 或达到 max_iterations 终止

简历点：工具循环的工程细节——并行 tool call、单条结果截断、工具异常回喂
模型重试、迭代上限防死循环、调用日志（供 evidence_refs / 可观测）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.agent.tools.registry import Tool, ToolContext, tool_schemas
from app.core.config import get_settings
from app.rag.client import LLMClient

logger = logging.getLogger(__name__)

settings = get_settings()


class ToolCallRecord:
    """单次工具调用记录（供 evidence_refs 与 Langfuse 观测）。"""

    def __init__(self, name: str, arguments: dict, doc_ids: list[str], ok: bool, ms: int):
        self.name = name
        self.arguments = arguments
        self.doc_ids = doc_ids
        self.ok = ok
        self.ms = ms

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "doc_ids": self.doc_ids,
            "ok": self.ok,
            "ms": self.ms,
        }


async def _run_tool(
    tool_call: Any, tools: dict[str, Tool], ctx: ToolContext
) -> tuple[str, ToolCallRecord]:
    """执行单个工具调用；异常/超长结果做防御处理。"""
    name = tool_call.function.name
    tool = tools.get(name)
    if tool is None:
        return f"（未知工具 {name}）", ToolCallRecord(name, {}, [], False, 0)
    try:
        args = json.loads(tool_call.function.arguments or "{}")
        if not isinstance(args, dict):
            args = {}
    except Exception:  # noqa: BLE001
        args = {}
    start = time.monotonic()
    try:
        text, doc_ids = await tool.handler(args, ctx)
        ok = True
    except Exception as exc:  # noqa: BLE001 工具异常回喂模型，允许其换参重试
        text, doc_ids, ok = f"（工具执行失败：{exc}）", [], False
    ms = int((time.monotonic() - start) * 1000)
    if len(text) > settings.tool_result_max_chars:
        text = text[: settings.tool_result_max_chars] + "\n…（结果已截断）"
    return text, ToolCallRecord(name, args, doc_ids, ok, ms)


async def call_llm_with_tools(
    client: LLMClient,
    messages: list[dict],
    tools: list[Tool],
    model: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    max_iterations: int | None = None,
    context: ToolContext | None = None,
) -> tuple[str, list[ToolCallRecord]]:
    """工具循环主入口：返回（最终文本, 工具调用日志）。

    - max_iterations 防死循环（默认取 config）；
    - 每轮：模型返回 tool_calls → 并行执行 → 追加 assistant(tool_calls) + tool 消息；
    - 无 tool_calls 时返回当前轮文本。
    """
    max_iterations = max_iterations or settings.agent_max_tool_iterations
    if not settings.agent_tool_calling_enabled:
        # 总开关关闭：跳过工具循环，直接文本生成
        text = await client.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)
        return text, []

    tools_by_name = {t.name: t for t in tools}
    schemas = tool_schemas(tools)
    ctx = context or {}
    records: list[ToolCallRecord] = []
    loop_messages: list[dict] = list(messages)

    for _ in range(max_iterations):
        message = await client.chat_with_tools(
            loop_messages,
            schemas,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            return message.content or "", records

        # 并行执行所有 tool call
        results = await asyncio.gather(
            *[_run_tool(tc, tools_by_name, ctx) for tc in tool_calls]
        )
        assistant_payload: dict[str, Any] = {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        }
        loop_messages.append(assistant_payload)
        for tc, (text, record) in zip(tool_calls, results, strict=True):
            records.append(record)
            loop_messages.append({"role": "tool", "tool_call_id": tc.id, "content": text})
        logger.info("tool round: %d calls, %d ms total", len(tool_calls), sum(r.ms for r in records))

    # 达到迭代上限：强制收敛——追加“禁止再调工具”的 user 消息，取最终文本
    # （否则最后一轮 tool 消息会被当成答案返回，如"（模板库不可用）"）
    loop_messages.append(
        {
            "role": "user",
            "content": "你已多次调用工具。请仅基于以上工具结果直接输出最终答案（严格按要求的 JSON 格式，禁止再调用任何工具）。",
        }
    )
    try:
        final_message = await client.chat(
            loop_messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        return final_message or "", records
    except Exception as exc:  # noqa: BLE001
        logger.warning("final convergence chat failed: %s", exc)
        return "", records
