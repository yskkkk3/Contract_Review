"""Admin configuration must affect actual calls, including streaming and fallback."""
from types import SimpleNamespace

import pytest

from app.agent.prompts import load_prompt
from app.core.db import SessionLocal
from app.core.runtime_config import model_config, prompt_scope, read_runtime, use_runtime


@pytest.fixture()
def provider(monkeypatch):
    from app.rag import client as module

    calls = []

    class FakeProvider:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
            self.embeddings = SimpleNamespace(create=self.embed)

        async def create(self, **kwargs):
            calls.append((self.options, kwargs))
            if kwargs.get("stream"):
                async def stream():
                    yield SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content="answer"))])
                return stream()
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))])

        async def embed(self, **kwargs):
            calls.append((self.options, kwargs))
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1])])

        async def close(self):
            await self.options["http_client"].aclose()

    monkeypatch.setattr(module, "AsyncOpenAI", FakeProvider)
    monkeypatch.setattr(module.settings, "llm_allowed_models", "")
    monkeypatch.setattr(module.settings, "llm_api_key", "test-fallback")
    monkeypatch.setattr(module.settings, "embedding_api_key", "test-embedding")
    return module.LLMClient(), calls


def snapshot():
    with SessionLocal() as db:
        return read_runtime(db)


def create_model(client, headers, role="chat", **overrides):
    response = client.post("/api/model-configs", headers=headers, json={
        "model_name": f"configured-{role}", "model_type": role,
        "api_endpoint": "https://configured.example/v1", "api_key": "env:TEST_MODEL_KEY",
        "is_default": 1, "temperature": 0.3, "top_p": 0.8, "max_tokens": 800, **overrides,
    })
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


async def test_all_inference_entrypoints_use_admin_provider_and_parameters(client, admin_headers, provider, monkeypatch):
    llm, calls = provider
    monkeypatch.setenv("TEST_MODEL_KEY", "test-referenced-value")
    for role in ("review", "chat", "intent", "embedding"):
        create_model(client, admin_headers, role)
    with use_runtime(snapshot()):
        await llm.chat([], max_tokens=2000)
        await llm.chat_with_tools([], [], max_tokens=256)
        await llm.chat_structured([], {"type": "object"})
        events = [event async for event in llm.chat_stream_events([])]
        await llm.embed(["question"])
    assert events[1] == ("delta", "answer")
    assert [request["model"] for _, request in calls] == [
        "configured-review", "configured-review", "configured-intent", "configured-chat", "configured-embedding",
    ]
    assert calls[0][1]["max_tokens"] == 800
    assert calls[1][1]["max_tokens"] == 256
    assert calls[0][1]["temperature"] == 0.3 and calls[0][1]["top_p"] == 0.8
    assert all(options["base_url"] == "https://configured.example/v1" for options, _ in calls)
    assert all(options["api_key"] == "test-referenced-value" for options, _ in calls)
    await llm.aclose()


async def test_structured_fallback_retains_role_and_allowlist(client, admin_headers, provider, monkeypatch):
    llm, calls = provider
    monkeypatch.setenv("TEST_MODEL_KEY", "reference")
    create_model(client, admin_headers, "review")
    create_model(client, admin_headers, "intent")
    with use_runtime(snapshot()):
        upstream = llm._provider("review")
        real = upstream.create

        async def fallback(**kwargs):
            if "response_format" in kwargs:
                raise ValueError("Unsupported structured format")
            return await real(**kwargs)

        monkeypatch.setattr(upstream.chat.completions, "create", fallback)
        assert await llm.chat_structured([], {}, model_type="review") == {"ok": True}
        assert calls[-1][1]["model"] == "configured-review"
        llm._allowed_models = {"another-model"}
        with pytest.raises(ValueError, match="LLM_ALLOWED_MODELS"):
            await llm.chat([])
    await llm.aclose()


async def test_rerank_uses_full_admin_endpoint(client, admin_headers, provider, monkeypatch):
    llm, _ = provider
    monkeypatch.setenv("TEST_MODEL_KEY", "reference")
    create_model(client, admin_headers, "rerank", api_endpoint="https://configured.example/reranks")
    captured = []

    async def post(url, **kwargs):
        captured.append((url, kwargs))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"results": []})

    monkeypatch.setattr(llm.http, "post", post)
    with use_runtime(snapshot()):
        assert await llm.rerank("q", ["doc"]) == []
    assert captured[0][0] == "https://configured.example/reranks"
    assert captured[0][1]["headers"]["Authorization"] == "Bearer reference"
    assert captured[0][1]["json"]["model"] == "configured-rerank"
    await llm.aclose()


def test_default_replacement_disable_and_snapshot_stability(client, admin_headers):
    first = create_model(client, admin_headers, model_name="first")
    old = snapshot()
    second = create_model(client, admin_headers, model_name="second")
    with use_runtime(old):
        assert model_config("chat")["model_name"] == "first"
    with use_runtime(snapshot()):
        assert model_config("chat")["model_name"] == "second"
    assert client.put(f"/api/model-configs/{second}", headers=admin_headers, json={"status": "inactive"}).status_code == 200
    with use_runtime(snapshot()):
        assert model_config("chat") is None
    rows = client.get("/api/model-configs", headers=admin_headers).json()["data"]
    assert next(r for r in rows if r["id"] == first)["is_default"] == 0


def create_prompt(client, headers, content, **values):
    response = client.post("/api/prompts", headers=headers, json={
        "level": "system", "prompt_name": "chat", "prompt_content": content, **values,
    })
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def test_prompt_chain_scope_and_inactive_parent(client, admin_headers):
    types = client.get("/api/contract-types", headers=admin_headers).json()["data"]
    type_id = types[0]["id"]
    base = create_prompt(client, admin_headers, "global {stance}")
    scoped = create_prompt(client, admin_headers, "scoped {stance}", contract_type_id=type_id)
    child = create_prompt(client, admin_headers, "derived {stance}", level="org", base_prompt_id=scoped, contract_type_id=type_id)
    with use_runtime(snapshot()):
        assert load_prompt("chat", stance="甲方") == "global 甲方"
        with prompt_scope(type_id):
            assert load_prompt("chat", stance="乙方") == "derived 乙方"
    assert client.put(f"/api/prompts/{scoped}", headers=admin_headers, json={"is_active": 0}).status_code == 200
    with use_runtime(snapshot()), prompt_scope(type_id):
        assert load_prompt("chat", stance="甲方") == "global 甲方"
    assert client.delete(f"/api/prompts/{scoped}", headers=admin_headers).status_code == 409
    assert client.delete(f"/api/prompts/{child}", headers=admin_headers).status_code == 200
    client.put(f"/api/prompts/{base}", headers=admin_headers, json={"is_active": 0})
    with use_runtime(snapshot()):
        assert load_prompt("chat") != "global {stance}"


@pytest.mark.parametrize("body", [
    {"api_key": "plaintext-credential"}, {"api_endpoint": "https://user:password@example.com"},
    {"max_tokens": -1}, {"top_p": 5},
])
def test_invalid_model_config_is_422_not_persisted(client, admin_headers, body):
    response = client.post("/api/model-configs", headers=admin_headers, json={
        "model_name": "model", "model_type": "chat", **body,
    })
    assert response.status_code == 422
    assert client.get("/api/model-configs", headers=admin_headers).json()["data"] == []


def test_unknown_template_or_unimplemented_organization_is_rejected(client, admin_headers):
    for fields in ({"prompt_name": "unused-name"}, {"organization_id": 1}):
        response = client.post("/api/prompts", headers=admin_headers, json={
            "level": "system", "prompt_name": "chat", "prompt_content": "test", **fields,
        })
        assert response.status_code == 422


def test_chat_api_loads_prompt_again_on_next_request(client, admin_headers, monkeypatch):
    from app.services import chat_service

    seen = []

    class FakeClient:
        async def chat_stream_events(self, messages, **kwargs):
            seen.append(messages[0]["content"])
            yield "delta", "answer"

    monkeypatch.setattr(chat_service, "get_sf_client", FakeClient)
    pid = create_prompt(client, admin_headers, "first system")
    sid = client.post("/api/sessions", headers=admin_headers, json={"title": "chat", "session_type": "chat"}).json()["data"]["session_id"]
    for content in ("first system", "second system"):
        client.put(f"/api/prompts/{pid}", headers=admin_headers, json={"prompt_content": content})
        response = client.post("/api/chats", headers=admin_headers, json={"session_id": sid, "content": "hello"})
        assert '"type": "done"' in response.text
    assert seen == ["first system", "second system"]


def test_dotenv_credential_reference_and_environment_precedence(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.core.runtime_config import credential

    path = tmp_path / ".env"
    path.write_text("AUDIT_MODEL_KEY=dotenv-test-value\n", encoding="utf-8")
    monkeypatch.setitem(get_settings().model_config, "env_file", (str(path),))
    monkeypatch.delenv("AUDIT_MODEL_KEY", raising=False)
    assert credential("env:AUDIT_MODEL_KEY", "fallback") == "dotenv-test-value"
    monkeypatch.setenv("AUDIT_MODEL_KEY", "environment-test-value")
    assert credential("env:AUDIT_MODEL_KEY", "fallback") == "environment-test-value"


async def test_missing_credentials_fail_before_provider_call(provider, monkeypatch):
    llm, calls = provider
    llm.api_key = ""
    with pytest.raises(ValueError, match="credential"):
        await llm.chat([])
    assert calls == []
    await llm.aclose()


async def test_ingestion_and_standalone_jobs_use_the_same_configuration(client, admin_headers):
    from app.core.runtime_config import runtime_job

    create_model(client, admin_headers)
    create_prompt(client, admin_headers, "job template")

    @runtime_job
    async def job():
        return model_config("chat")["model_name"], load_prompt("chat")

    assert await job() == ("configured-chat", "job template")
    assert model_config("chat") is None


@pytest.mark.parametrize("body", [{"model_name": None}, {"max_tokens": None}, {"status": None}])
def test_null_model_updates_do_not_corrupt_active_configuration(client, admin_headers, body):
    mid = create_model(client, admin_headers)
    assert client.put(f"/api/model-configs/{mid}", headers=admin_headers, json=body).status_code == 422
    assert snapshot().models["chat"]["model_name"] == "configured-chat"


async def test_expansion_cache_invalidates_when_prompt_changes(client, admin_headers, monkeypatch):
    from app.rag import query_expansion as module

    calls = []

    class FakeClient:
        async def chat(self, messages, **kwargs):
            calls.append(messages[0]["content"])
            assert kwargs["model_type"] == "intent"
            return '["expanded"]'

    monkeypatch.setattr(module, "get_sf_client", FakeClient)
    monkeypatch.setattr(module, "_cache", module._TTLCache())
    pid = create_prompt(client, admin_headers, "first", prompt_name="rag_query_expansion")
    with use_runtime(snapshot()):
        await module.expand_query("unique-question", variants=2)
        await module.expand_query("unique-question", variants=2)
    client.put(f"/api/prompts/{pid}", headers=admin_headers, json={"prompt_content": "second"})
    with use_runtime(snapshot()):
        await module.expand_query("unique-question", variants=2)
    assert calls == ["first", "second"]


def test_enabling_prompt_version_replaces_the_same_scope(client, admin_headers):
    old = create_prompt(client, admin_headers, "old")
    new = create_prompt(client, admin_headers, "new")
    with use_runtime(snapshot()):
        assert load_prompt("chat") == "new"
    client.put(f"/api/prompts/{old}", headers=admin_headers, json={"is_active": 1})
    with use_runtime(snapshot()):
        assert load_prompt("chat") == "old"
    rows = client.get("/api/prompts", headers=admin_headers).json()["data"]
    assert next(row for row in rows if row["id"] == new)["is_active"] == 0


def test_review_api_keeps_configuration_and_contract_scope_in_stream(client, admin_headers, tmp_path, monkeypatch):
    from app.core.security import decode_token
    from app.models.contract import ContractFile
    from app.services import review_service

    type_id = client.get("/api/contract-types", headers=admin_headers).json()["data"][0]["id"]
    create_model(client, admin_headers, "review")
    create_prompt(client, admin_headers, "scoped specialist {risk_dim}", prompt_name="specialist_base", contract_type_id=type_id)
    parsed = tmp_path / "contract.txt"
    parsed.write_text("第一条 合同双方按约定验收付款。", encoding="utf-8")
    with SessionLocal() as db:
        record = ContractFile(
            user_id=decode_token(admin_headers["Authorization"][7:])["user_id"],
            title="contract", file_type="docx", file_path="unused", content_path=str(parsed), contract_type_id=type_id,
        )
        db.add(record)
        db.commit()
        file_id = record.id
    sid = client.post("/api/sessions", headers=admin_headers, json={
        "title": "review", "session_type": "review", "file_id": file_id,
    }).json()["data"]["session_id"]
    seen = []

    class Graph:
        async def astream(self, *args, **kwargs):
            seen.append((model_config("review")["model_name"], load_prompt("specialist_base", risk_dim="付款")))
            yield "updates", {"arbitration": {"final_risk_points": [], "summary": {"review_status": "completed"}}}

    monkeypatch.setattr(review_service, "get_graph", lambda _: Graph())
    monkeypatch.setattr(review_service, "get_rag_service", object)
    response = client.post("/api/reviews/start", headers=admin_headers, json={"session_id": sid, "stance": "甲方"})
    assert '"event": "end"' in response.text
    assert seen == [("configured-review", "scoped specialist 付款")]
