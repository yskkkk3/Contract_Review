"""Test fixtures: SQLite in-memory DB + fakeredis + app dependency overrides."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-0123456789abcdef")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("UPLOAD_DIR", "/tmp/contract-review-uploads")
os.environ.setdefault("OSS_BUCKET_DIR", "/tmp/contract-review-parsed")
os.environ.setdefault("STORAGE_BACKEND", "local")

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

import app.core.redis as redis_mod
import app.main as main_mod
from app.core.db import Base, engine, get_db
from app.main import app


class FakeLLMClient:
    """全局替换 LLM 客户端：CI/本地测试均不依赖真实 API key。"""

    async def chat(self, *args, **kwargs):
        return "{}"

    async def chat_stream(self, *args, **kwargs):
        yield "[STREAM_DONE]"

    async def chat_stream_events(self, *args, **kwargs):
        yield ("start", None)
        yield ("delta", "[STREAM_DONE]")
        yield ("usage", {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

    async def embed(self, texts: list[str], *args, **kwargs):
        return [[0.0] * 1024 for _ in texts]

    async def rerank(self, query: str, docs: list[str], *args, **kwargs):
        return [{"index": i, "relevance_score": 0.0} for i in range(len(docs))]


@pytest.fixture(autouse=True)
def _mock_llm_client(monkeypatch):
    """避免任何测试路径构造真实 AsyncOpenAI（无 key 时 OpenAI SDK 会抛
    Missing credentials，CI 无 .env 即失败；本地通过是依赖 .env 的假象）。"""
    from app.rag import client as client_mod

    monkeypatch.setattr(client_mod, "get_sf_client", lambda: FakeLLMClient())


@pytest.fixture()
def client():
    # in-memory SQLite: create schema per test
    Base.metadata.create_all(bind=engine)

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    redis_mod.redis_client = fake_redis

    async def _noop() -> None:
        return None

    # 跳过 lifespan 中的真实 Redis 初始化
    main_mod.init_redis = _noop  # type: ignore[assignment]
    main_mod.close_redis = _noop  # type: ignore[assignment]

    def override_get_db():
        from app.core.db import SessionLocal

        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    redis_mod.redis_client = None
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def auth_headers(client):
    """注册并登录，返回带 Authorization 的请求头。"""
    resp = client.post("/api/users", json={"username": "tester", "password": "secret123"})
    assert resp.status_code == 200, resp.text
    login = client.post(
        "/api/auth/login", json={"identifier": "tester", "password": "secret123"}
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
