"""LLMClient 工程化测试：限流、缓存与多供应商路由。"""
from __future__ import annotations

import asyncio

import pytest

import app.rag.client as client_mod
from app.rag.client import LLMClient


class _FakeChoice:
    def __init__(self, text: str = "ok", tool_calls=None):
        self.message = type(
            "Msg",
            (),
            {"content": text, "tool_calls": tool_calls, "finish_reason": "stop"},
        )()


class _FakeResp:
    def __init__(self, text: str = "ok"):
        self.choices = [_FakeChoice(text)]


@pytest.fixture
def fake_openai(monkeypatch):
    """CI 无 .env：mock AsyncOpenAI 构造，避免 openai SDK 强制校验 API key。"""

    monkeypatch.setattr(client_mod.settings, "llm_allowed_models", "")

    class _FakeCompletions:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": type("Comp", (), {"create": None})()})()
            self.embeddings = type("Emb", (), {"create": None})()

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.init_kwargs = kwargs
            self.chat = type("Chat", (), {"completions": type("Comp", (), {"create": None})()})()
            self.embeddings = type("Emb", (), {"create": None})()

    monkeypatch.setattr(client_mod, "AsyncOpenAI", _FakeAsyncOpenAI)
    return _FakeAsyncOpenAI


@pytest.mark.parametrize("method", ["chat", "chat_with_tools", "chat_structured", "collect_stream", "chat_stream", "chat_stream_events"])
async def test_model_cost_policy_blocks_every_inference_entry_before_network(monkeypatch, fake_openai, method):
    monkeypatch.setattr(client_mod.settings, "llm_allowed_models", " deepseek-v4.1-flash ")
    client = LLMClient()

    async def unexpected(**kwargs):
        pytest.fail("Disallowed model must not reach the provider")

    monkeypatch.setattr(client._openai.chat.completions, "create", unexpected)
    kwargs = {"model": "deepseek-v4-pro"}
    if method == "chat_with_tools":
        kwargs["tools"] = []
    if method == "chat_structured":
        kwargs["json_schema"] = {"type": "object"}
    try:
        with pytest.raises(ValueError, match="LLM_ALLOWED_MODELS"):
            result = getattr(client, method)([], **kwargs)
            if method in {"chat_stream", "chat_stream_events"}:
                [item async for item in result]
            else:
                await result
    finally:
        await client._openai.init_kwargs["http_client"].aclose()
        await client._embedding_openai.init_kwargs["http_client"].aclose()


async def test_allowed_model_works_but_misconfigured_default_is_blocked(monkeypatch, fake_openai):
    monkeypatch.setattr(client_mod.settings, "llm_allowed_models", "deepseek-v4.1-flash")
    monkeypatch.setattr(client_mod.settings, "llm_review_model", "deepseek-v4-pro")
    client = LLMClient()

    async def create(**kwargs):
        assert kwargs["model"] == "deepseek-v4.1-flash"
        return _FakeResp("OK")

    monkeypatch.setattr(client._openai.chat.completions, "create", create)
    try:
        with pytest.raises(ValueError, match="LLM_ALLOWED_MODELS"):
            await client.chat([])
        assert await client.chat([], model="deepseek-v4.1-flash") == "OK"
    finally:
        await client._openai.init_kwargs["http_client"].aclose()
        await client._embedding_openai.init_kwargs["http_client"].aclose()


@pytest.mark.parametrize("trust_env", [True, False])
async def test_proxy_policy_applies_to_inference_embedding_and_rerank(monkeypatch, fake_openai, trust_env):
    monkeypatch.setattr(client_mod.settings, "llm_http_trust_env", trust_env)
    client = LLMClient()
    inference = client._openai.init_kwargs["http_client"]
    embedding = client._embedding_openai.init_kwargs["http_client"]
    try:
        assert inference.trust_env is trust_env
        assert embedding.trust_env is trust_env
        assert client.http.trust_env is trust_env
    finally:
        await inference.aclose()
        await embedding.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_chat_acquires_semaphore(monkeypatch, fake_openai):
    """并发上限：超过 MAX_CONCURRENT_LLM 的调用必须排队（信号量生效）。"""
    client = LLMClient()
    client._sem = asyncio.Semaphore(2)

    active = 0
    peak = 0
    gate = asyncio.Event()

    async def fake_create(**kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        gate.set()
        return _FakeResp()

    monkeypatch.setattr(client._openai.chat.completions, "create", fake_create)

    results = await asyncio.gather(*[client.chat([{"role": "user", "content": "x"}]) for _ in range(6)])
    assert results == ["ok"] * 6
    assert peak <= 2, f"并发峰值 {peak} 超出信号量上限 2"


@pytest.mark.asyncio
async def test_chat_with_tools_acquires_semaphore(monkeypatch, fake_openai):
    client = LLMClient()
    client._sem = asyncio.Semaphore(1)

    async def fake_create(**kwargs):
        await asyncio.sleep(0.02)
        return _FakeResp()

    monkeypatch.setattr(client._openai.chat.completions, "create", fake_create)
    msg = await client.chat_with_tools([{"role": "user", "content": "x"}], tools=[{"type": "function", "function": {"name": "f", "parameters": {"type": "object"}}}])
    assert msg.content == "ok"


@pytest.mark.asyncio
async def test_prompt_cache_extra_body(monkeypatch, fake_openai):
    """开启 prompt cache 时 extra_body 带 cache_prompt=True。"""
    client = LLMClient()
    client._prompt_cache = True
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeResp()

    monkeypatch.setattr(client._openai.chat.completions, "create", fake_create)
    await client.chat([{"role": "user", "content": "hi"}])
    assert captured["extra_body"]["cache_prompt"] is True


@pytest.mark.asyncio
async def test_prompt_cache_disabled(monkeypatch, fake_openai):
    client = LLMClient()
    client._prompt_cache = False
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeResp()

    monkeypatch.setattr(client._openai.chat.completions, "create", fake_create)
    await client.chat([{"role": "user", "content": "hi"}])
    assert "extra_body" not in captured


@pytest.mark.asyncio
async def test_brief_deepseek_tasks_preserve_output_budget(monkeypatch, fake_openai):
    monkeypatch.setattr(client_mod.settings, "llm_brief_disable_thinking", None)
    client = LLMClient()
    client.base_url = "https://api.deepseek.com/v1"
    client._prompt_cache = True
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return _FakeResp('{"valid":true}')

    monkeypatch.setattr(client._openai.chat.completions, "create", create)
    await client.chat([{"role": "user", "content": "短任务"}], brief=True)
    assert captured["extra_body"] == {"thinking": {"type": "disabled"}, "cache_prompt": True}
    await client.chat_structured([], json_schema={"type": "object"})
    assert captured["extra_body"]["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_brief_other_providers_receive_no_deepseek_options(monkeypatch, fake_openai):
    monkeypatch.setattr(client_mod.settings, "llm_brief_disable_thinking", None)
    client = LLMClient()
    client.base_url = "https://example.org/v1"
    client._prompt_cache = False
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return _FakeResp()

    monkeypatch.setattr(client._openai.chat.completions, "create", create)
    await client.chat([], brief=True)
    assert "extra_body" not in captured


@pytest.mark.asyncio
async def test_brief_thinking_control_is_explicit_for_compatible_relays(monkeypatch, fake_openai):
    client = LLMClient()
    client.base_url = "https://relay.example/v1"
    client._prompt_cache = False
    captured = {}

    async def create(**kwargs):
        captured.clear()
        captured.update(kwargs)
        return _FakeResp('{"ok":true}')

    monkeypatch.setattr(client._openai.chat.completions, "create", create)
    monkeypatch.setattr(client_mod.settings, "llm_brief_disable_thinking", True)
    await client.chat([], brief=True)
    assert captured["extra_body"]["thinking"] == {"type": "disabled"}
    await client.chat([], brief=False)
    assert "extra_body" not in captured
    monkeypatch.setattr(client_mod.settings, "llm_brief_disable_thinking", False)
    client.base_url = "https://api.deepseek.com"
    await client.chat([], brief=True)
    assert "extra_body" not in captured


@pytest.mark.asyncio
async def test_structured_billing_failure_does_not_retry_as_format_fallback(monkeypatch, fake_openai):
    client = LLMClient()
    calls = 0

    class BillingError(Exception):
        status_code = 402

    async def fail(**kwargs):
        nonlocal calls
        calls += 1
        raise BillingError("balance unavailable")

    monkeypatch.setattr(client._openai.chat.completions, "create", fail)
    with pytest.raises(BillingError):
        await client.chat_structured([], json_schema={"type": "object"})
    assert calls == 1


@pytest.mark.parametrize("transport", ["sdk", "httpx"])
async def test_dashscope_arrearage_does_not_trigger_paid_format_retry(monkeypatch, fake_openai, transport):
    import httpx

    client = LLMClient()
    calls = 0
    if transport == "sdk":
        error = type("BillingError", (Exception,), {
            "status_code": 400, "body": {"error": {"code": "Arrearage"}},
        })("billing unavailable")
    else:
        response = httpx.Response(400, json={"code": "Arrearage"},
                                  request=httpx.Request("POST", "https://example.org/reranks"))
        error = httpx.HTTPStatusError("billing unavailable", request=response.request, response=response)

    async def fail(**kwargs):
        nonlocal calls
        calls += 1
        raise error

    monkeypatch.setattr(client._openai.chat.completions, "create", fail)
    with pytest.raises(type(error)):
        await client.chat_structured([], json_schema={"type": "object"})
    assert calls == 1
    assert client_mod.provider_status_code(error) == 400
    assert client_mod.provider_error_code(error) == "Arrearage"


async def test_nonbilling_bad_request_can_still_fall_back_to_plain_json(monkeypatch, fake_openai):
    import httpx

    client = LLMClient()
    calls = 0

    async def create(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            response = httpx.Response(400, json={"code": "InvalidParameter"},
                                      request=httpx.Request("POST", "https://example.org/chat/completions"))
            raise httpx.HTTPStatusError("unsupported schema", request=response.request, response=response)
        return _FakeResp('{"ok":true}')

    monkeypatch.setattr(client._openai.chat.completions, "create", create)
    assert await client.chat_structured([], json_schema={"type": "object"}) == {"ok": True}
    assert calls == 2


@pytest.mark.asyncio
async def test_embed_uses_independent_embedding_client(monkeypatch, fake_openai):
    client = LLMClient()
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        item_1 = type("Embedding", (), {"index": 1, "embedding": [0.3, 0.4]})()
        item_0 = type("Embedding", (), {"index": 0, "embedding": [0.1, 0.2]})()
        return type("Response", (), {"data": [item_1, item_0]})()

    monkeypatch.setattr(client._embedding_openai.embeddings, "create", fake_create)
    vectors = await client.embed(["a", "b"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["model"] == client_mod.settings.embedding_model
    assert captured["dimensions"] == client_mod.settings.embedding_dimensions


@pytest.mark.asyncio
async def test_rerank_uses_independent_endpoint(monkeypatch, fake_openai):
    client = LLMClient()
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"index": 0, "relevance_score": 0.99}]}

    class _Http:
        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return _Response()

    client._http = _Http()
    result = await client.rerank("付款期限", ["甲方应付款"], top_n=1)

    assert captured["url"] == client.rerank_url
    assert captured["json"]["model"] == client_mod.settings.rerank_model
    assert result[0]["relevance_score"] == 0.99


@pytest.mark.asyncio
async def test_chat_stream_events_cache_and_semaphore(monkeypatch, fake_openai):
    client = LLMClient()
    client._sem = asyncio.Semaphore(1)
    client._prompt_cache = True
    captured = {}

    class _FakeChunk:
        def __init__(self):
            self.usage = None
            self.choices = [type("C", (), {"delta": type("D", (), {"content": "a"})()})()]

    class _FakeStream:
        def __init__(self):
            self._chunks = [_FakeChunk()]

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._chunks:
                raise StopAsyncIteration
            return self._chunks.pop(0)

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeStream()

    monkeypatch.setattr(client._openai.chat.completions, "create", fake_create)
    events = [e async for e in client.chat_stream_events([{"role": "user", "content": "hi"}])]
    assert events[0] == ("start", None)
    assert events[-1] == ("delta", "a")
    assert captured["extra_body"]["cache_prompt"] is True
