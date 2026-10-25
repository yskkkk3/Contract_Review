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
from app.core.langfuse import observation, traced
from app.core.runtime_config import credential, model_config

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
            api_key=self.api_key or "unconfigured",
            timeout=self.timeout,
            max_retries=1,
            http_client=DefaultAsyncHttpxClient(trust_env=settings.llm_http_trust_env),
        )
        self._embedding_openai = AsyncOpenAI(
            base_url=self.embedding_base_url,
            api_key=self.embedding_api_key or "unconfigured",
            timeout=self.timeout,
            max_retries=1,
            http_client=DefaultAsyncHttpxClient(trust_env=settings.llm_http_trust_env),
        )
        self._http: httpx.AsyncClient | None = None
        self._providers: dict[tuple[str, str], Any] = {}
        # 应用层并发限流：所有 LLM 调用共享信号量，防止突发请求打满供应商推理队列
        self._sem = asyncio.Semaphore(settings.max_concurrent_llm)
        background_slots = max(1, settings.max_concurrent_llm - settings.llm_chat_reserved_slots)
        self._background_sem = asyncio.Semaphore(background_slots)
        self._prompt_cache = settings.llm_prompt_cache

    def _provider(self, role: str):
        config = model_config(role)
        default = self._embedding_openai if role == "embedding" else self._openai
        fallback_key = self.embedding_api_key if role == "embedding" else self.api_key
        if not config:
            if not fallback_key:
                raise ValueError("Model credential is missing")
            return default
        fallback_url = self.embedding_base_url if role == "embedding" else self.base_url
        endpoint = config["api_endpoint"] or fallback_url
        key = credential(config["api_key"], fallback_key)
        if not key:
            raise ValueError("Configured model has no credential")
        identity = (endpoint, key)
        if identity not in self._providers:
            self._providers[identity] = AsyncOpenAI(
                base_url=endpoint, api_key=key, timeout=self.timeout, max_retries=1,
                http_client=DefaultAsyncHttpxClient(trust_env=settings.llm_http_trust_env),
            )
        return self._providers[identity]

    def _options(self, role: str, model: str, options: dict) -> tuple[str, dict]:
        options = dict(options)
        config = model_config(role)
        if config:
            model = config["model_name"]
            if role not in {"embedding", "rerank"}:
                options["temperature"] = config["temperature"]
                options["top_p"] = config["top_p"]
                options["max_tokens"] = min(options.get("max_tokens", config["max_tokens"]), config["max_tokens"])
        if role not in {"embedding", "rerank"}:
            model = self._checked_model(model)
        return model, options

    async def _complete(self, role: str, model: str, **options):
        model, options = self._options(role, model, options)
        with observation("llm.complete", as_type="generation", model=model) as span:
            response = await self._provider(role).chat.completions.create(model=model, **options)
            usage = getattr(response, "usage", None)
            if usage:
                span.update(usage_details={
                    "input": usage.prompt_tokens, "output": usage.completion_tokens,
                })
            return response

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
            role = kwargs.pop("model_type", "chat")
            model, options = self._options(role, model, self._apply_cache(kwargs))
            with observation("llm.stream", as_type="generation", model=model) as span:
                stream = await self._provider(role).chat.completions.create(
                    model=model, messages=messages, stream=True, **options,
                )
                async def tracked():
                    async for chunk in stream:
                        usage = getattr(chunk, "usage", None)
                        if usage:
                            span.update(usage_details={"input": usage.prompt_tokens, "output": usage.completion_tokens})
                        yield chunk

                try:
                    from contextlib import aclosing

                    async with aclosing(tracked()) as source:
                        yield source
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

    def _task_options(self, kwargs: dict, brief: bool, role: str = "review") -> dict:
        """短结构化任务不应把输出预算全部消耗在 DeepSeek thinking 中。"""
        disable_thinking = settings.llm_brief_disable_thinking
        if disable_thinking is None:
            config = model_config(role)
            endpoint = config["api_endpoint"] if config else self.base_url
            disable_thinking = urlsplit(endpoint).hostname == "api.deepseek.com"
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
        for provider in [self._openai, self._embedding_openai, *self._providers.values()]:
            close = getattr(provider, "close", None)
            if close:
                await close()
        self._providers.clear()

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
        model = model or settings.llm_review_model
        role = kwargs.pop("model_type", "review")
        async with self._request_slot():
            resp = await self._complete(
                role, model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **self._task_options(kwargs, brief, role),
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
        model = model or settings.llm_review_model
        role = kwargs.pop("model_type", "review")
        async with self._request_slot():
            resp = await self._complete(
                role, model,
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
        model = model or settings.llm_intent_model
        role = kwargs.pop("model_type", "intent")
        model, _ = self._options(role, model, {})
        try:
            async with self._request_slot():
                resp = await self._complete(
                    role, model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": "structured_output", "strict": True, "schema": json_schema},
                    },
                    **self._task_options(kwargs, brief, role),
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
                brief=brief, model_type=role, **kwargs,
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
        model = model or settings.llm_chat_model
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
        model = model or settings.llm_chat_model
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
        model = model or settings.llm_chat_model
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
    @traced("llm.embedding", as_type="embedding")
    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        model, _ = self._options("embedding", model or settings.embedding_model, {})
        async with self._request_slot():
            resp = await self._provider("embedding").embeddings.create(
                model=model,
                input=texts,
                encoding_format="float",
                dimensions=settings.embedding_dimensions,
            )
        ordered = sorted(resp.data, key=lambda x: x.index)
        return [item.embedding for item in ordered]

    # ---------- rerank（供应商扩展接口） ----------
    @traced("llm.rerank")
    async def rerank(
        self,
        query: str,
        documents: list[str],
        model: str | None = None,
        top_n: int = 5,
    ) -> list[dict]:
        model, _ = self._options("rerank", model or settings.rerank_model, {})
        config = model_config("rerank")
        endpoint = config["api_endpoint"] if config else self.rerank_url
        key = credential(config["api_key"], self.rerank_api_key) if config else self.rerank_api_key
        if not key:
            raise ValueError("Rerank credential is missing")
        headers = {"Authorization": "Bearer " + key} if config else {}
        async with self._request_slot():
            resp = await self.http.post(
                endpoint, **({"headers": headers} if config else {}),
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
