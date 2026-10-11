"""Qdrant client factory for server and local development modes."""

from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings

settings = get_settings()


def create_qdrant_client(timeout: float = 30.0) -> AsyncQdrantClient:
    if settings.qdrant_location:
        return AsyncQdrantClient(path=settings.qdrant_location)
    # 本地地址通常是 SSH 隧道，不应经过系统 HTTP_PROXY/HTTPS_PROXY。
    trust_env = settings.qdrant_host not in {"127.0.0.1", "localhost", "::1"}
    return AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=timeout,
        trust_env=trust_env,
    )
