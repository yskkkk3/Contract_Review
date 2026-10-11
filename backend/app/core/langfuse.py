"""Langfuse observability integration (self-hosted).

简历点：全链路可观测——审阅/聊天/检索调用埋点，trace 关联 session_id，
压测与线上问题定位依赖 trace 分析（见 docs/benchmark.md）。
"""

from app.core.config import get_settings

_lf = None


def get_langfuse():
    global _lf
    if _lf is not None:
        return _lf
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    try:
        from langfuse import Langfuse

        _lf = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            enabled=bool(settings.langfuse_public_key),
        )
        return _lf
    except Exception:  # noqa: BLE001
        return None
