"""模型客户端：推理、向量化和重排可分别接入不同供应商。

chat / embeddings 使用 OpenAI SDK；rerank 使用供应商兼容的 HTTP 接口。
默认组合为 DeepSeek 推理 + 阿里云百炼 Embedding/Rerank。
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

import httpx
from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from app.core.config import get_settings

settings = get_settings()


def provider_status_code(exc: Exception) -> int | None:
    """兼容OpenAI SDK与HTTPX供应商扩展接口的状态码。"""
    return getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)


def provider_error_code(exc: Exception) -> str | None:
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        response = getattr(exc, "response", None)
        try:
            body = response.json() if response is not None else None
        except ValueError:
            body = None
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return error["code"]
    return None


def is_provider_access_error(exc: Exception) -> bool:
    """认证、余额或权限失败不能通过换输出格式重试来恢复。"""
    return provider_status_code(exc) in {401, 402, 403} or provider_error_code(exc) == "Arrearage"


def _extract_json(raw: str) -> dict | None:
    """容错 JSON 提取：先整体解析，再取首个 {…} 块。"""
    import json
    import re

    raw = raw.strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                data = json.loads(match.group(0))
                return data if isinstance(data, dict) else None
            except Exception:  # noqa: BLE001
                return None
    return None


def _final_content(message: Any) -> str:
    """部分中转将reasoning_content重复拼进content，只保留可区分的最终正文。"""
    content = message.content or ""
    reasoning = getattr(message, "reasoning_content", None)
    if isinstance(reasoning, str) and reasoning and content.startswith(reasoning):
        return content[len(reasoning):].lstrip()
    return content


class LLMClient:
    def __init__(self) -> None:
        self.base_url = settings.effective_llm_base_url
        self.api_key = settings.effective_llm_api_key
        self.embedding_base_url = settings.effective_embedding_base_url
        self.embedding_api_key = settings.effective_embedding_api_key
        self.rerank_url = settings.effective_rerank_url
        self.rerank_api_key = settings.effective_rerank_api_key
        self.timeout = httpx.Timeout(120.0, connect=10.0)
        self._allowed_models = {
            item.strip() for item in settings.llm_allowed_models.split(",") if item.strip()
        }
        self._openai = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=1,
            http_client=DefaultAsyncHttpxClient(trust_env=settings.llm_http_trust_env),
        )
        self._embedding_openai = AsyncOpenAI(
            base_url=self.embedding_base_url,
            api_key=self.embedding_api_key,
            timeout=self.timeout,
            max_retries=1,
            http_client=DefaultAsyncHttpxClient(trust_env=settings.llm_http_trust_env),
        )
        self._http: httpx.AsyncClient | None = None
        # 应用层并发限流：所有 LLM 调用共享信号量，防止突发请求打满供应商推理队列
        self._sem = asyncio.Semaphore(settings.max_concurrent_llm)
        background_slots = max(1, settings.max_concurrent_llm - settings.llm_chat_reserved_slots)
        self._background_sem = asyncio.Semaphore(background_slots)
        self._prompt_cache = settings.llm_prompt_cache

    @asynccontextmanager
    async def _request_slot(self, *, interactive: bool = False):
        # Acquire the background gate first so queued review work cannot take chat's slot.
        if interactive:
            async with self._sem:
                yield
        else:
            async with self._background_sem, self._sem:
                yield

    @asynccontextmanager
    async def _stream(self, messages: list[dict], model: str, *, interactive: bool = False,
                      **kwargs: Any):
        async with self._request_slot(interactive=interactive):
            stream = await self._openai.chat.completions.create(
                model=model, messages=messages, stream=True, **self._apply_cache(kwargs),
            )
            try:
                yield stream
            finally:
                close = getattr(stream, "close", None)
                if close is not None:
                    await close()

    def _apply_cache(self, kwargs: dict) -> dict:
        """SiliconFlow prompt cache：命中后显著降低 prefill 耗时（TTFT 优化）。

        cache_prompt 是供应商扩展参数，OpenAI SDK 经 extra_body 透传；
        供应商不支持时忽略该字段即可。embedding 不走 prompt cache。
        """
        if self._prompt_cache:
            extra = dict(kwargs.get("extra_body") or {})
            extra.setdefault("cache_prompt", True)
            kwargs["extra_body"] = extra
        return kwargs

    def _checked_model(self, model: str) -> str:
        """所有推理入口在发送请求前检查，格式降级也不能越过成本限制。"""
        if self._allowed_models and model not in self._allowed_models:
            raise ValueError(f"Inference model {model!r} is not in LLM_ALLOWED_MODELS")
        return model

    def _task_options(self, kwargs: dict, brief: bool) -> dict:
        """短结构化任务不应把输出预算全部消耗在 DeepSeek thinking 中。"""
        disable_thinking = settings.llm_brief_disable_thinking
        if disable_thinking is None:
            disable_thinking = urlsplit(self.base_url).hostname == "api.deepseek.com"
        if brief and disable_thinking:
            extra = dict(kwargs.get("extra_body") or {})
            extra.setdefault("thinking", {"type": "disabled"})
            kwargs["extra_body"] = extra
        if brief and settings.llm_brief_reasoning_effort:
            kwargs.setdefault("reasoning_effort", settings.llm_brief_reasoning_effort)
        return self._apply_cache(kwargs)

    @property
    def http(self) -> httpx.AsyncClient:
        """供 rerank 等供应商扩展接口使用。"""
        if self._http is None:
            self._http = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.rerank_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(120.0, connect=10.0),
                trust_env=settings.llm_http_trust_env,
            )
        return self._http

    async def aclose(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # ---------- chat（OpenAI SDK） ----------
    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        brief: bool = False,
        **kwargs: Any,
    ) -> str:
        model = self._checked_model(model or settings.llm_review_model)
        async with self._request_slot():
            resp = await self._openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **self._task_options(kwargs, brief),
            )
        return _final_content(resp.choices[0].message)

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        tool_choice: str | dict = "auto",
        **kwargs: Any,
    ):
        """OpenAI SDK Tool Calling：返回完整 message（含 tool_calls / content）。

        调用方负责工具循环（见 app/agent/tools/executor.py）。
        """
        model = self._checked_model(model or settings.llm_review_model)
        async with self._request_slot():
            resp = await self._openai.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=max_tokens,
                **self._apply_cache(kwargs),
            )
        message = resp.choices[0].message
        message.content = _final_content(message)
        return message

    async def chat_structured(
        self,
        messages: list[dict],
        json_schema: dict,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
        brief: bool = True,
        **kwargs: Any,
    ) -> dict | None:
        """Structured output：response_format=json_schema 返回解析后的 dict。

        供应商不支持 strict json_schema 时回退普通 chat + 正则提取 JSON；
        解析失败返回 None，由调用方降级。
        """
        model = self._checked_model(model or settings.llm_intent_model)
        try:
            async with self._request_slot():
                resp = await self._openai.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": "structured_output", "strict": True, "schema": json_schema},
                    },
                    **self._task_options(kwargs, brief),
                )
            content = _final_content(resp.choices[0].message)
            parsed = _extract_json(content)
            if parsed is not None:
                return parsed
        except Exception as exc:  # noqa: BLE001 供应商不支持 json_schema → 走降级路径
            if is_provider_access_error(exc):
                raise
            pass
        try:
            raw = await self.chat(
                messages, model=model, temperature=temperature, max_tokens=max_tokens,
                brief=brief, **kwargs,
            )
            return _extract_json(raw)
        except Exception as exc:  # noqa: BLE001
            if is_provider_access_error(exc):
                raise
            return None

    async def collect_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        **kwargs: Any,
    ) -> tuple[str, dict]:
        """流式聚合：收集完整文本 + usage（include_usage）。

        供非增量场景（gate/arbitration）复用流式通道，顺带统计 token。
        """
        model = self._checked_model(model or settings.llm_chat_model)
        full: list[str] = []
        usage: dict = {}
        kwargs.setdefault("stream_options", {"include_usage": True})
        async with self._stream(messages, model, **kwargs) as stream:
            async for chunk in stream:
                if chunk.usage:
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    full.append(_final_content(chunk.choices[0].delta))
        return "".join(full), usage

    async def chat_stream(self, messages: list[dict], model: str | None = None, **kwargs: Any):
        """OpenAI SDK 流式：返回增量文本的异步生成器。

        调用方传 stream_options={"include_usage": True} 时，末尾会收到 usage chunk
        （无 content），由调用方统计；生成器本身只产出增量文本。
        """
        model = self._checked_model(model or settings.llm_chat_model)
        async with self._stream(messages, model, **kwargs) as stream:
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    text = _final_content(chunk.choices[0].delta)
                    if text:
                        yield text

    async def chat_stream_events(self, messages: list[dict], model: str | None = None, **kwargs: Any):
        """流式事件生成器：yield ("start", None) → ("delta", text)… → ("usage", dict)。

        供需要 TTFT / token 统计的流式链路（chat_service）使用。
        """
        model = self._checked_model(model or settings.llm_chat_model)
        kwargs.setdefault("stream_options", {"include_usage": True})
        async with self._stream(messages, model, interactive=True, **kwargs) as stream:
            yield ("start", None)
            async for chunk in stream:
                emitted = False
                # Independent checks: usage and content can share one chunk.
                if chunk.usage:
                    emitted = True
                    yield (
                        "usage",
                        {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens,
                        },
                    )
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    text = _final_content(chunk.choices[0].delta)
                    if text:
                        emitted = True
                        yield ("delta", text)
                if not emitted:
                    # Signal liveness without exposing private reasoning to the browser.
                    yield ("activity", None)

    # ---------- embedding（OpenAI SDK） ----------
    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        model = model or settings.embedding_model
        async with self._request_slot():
            resp = await self._embedding_openai.embeddings.create(
                model=model,
                input=texts,
                encoding_format="float",
                dimensions=settings.embedding_dimensions,
            )
        ordered = sorted(resp.data, key=lambda x: x.index)
        return [item.embedding for item in ordered]

    # ---------- rerank（供应商扩展接口） ----------
    async def rerank(
        self,
        query: str,
        documents: list[str],
        model: str | None = None,
        top_n: int = 5,
    ) -> list[dict]:
        model = model or settings.rerank_model
        async with self._request_slot():
            resp = await self.http.post(
                self.rerank_url,
                json={"model": model, "query": query, "documents": documents, "top_n": top_n},
            )
        resp.raise_for_status()
        return resp.json().get("results", [])


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


# 兼容旧调用方（agent 节点 / rag / 服务层）
get_sf_client = get_llm_client
