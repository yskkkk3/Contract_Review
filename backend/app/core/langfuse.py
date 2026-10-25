"""Optional Langfuse v4 tracing; telemetry failures never interrupt business work."""
import inspect
import logging
from contextlib import ExitStack, contextmanager
from functools import wraps

from app.core.config import get_settings

logger = logging.getLogger(__name__)
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
            public_key=settings.langfuse_public_key, secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_host, tracing_enabled=True, environment=settings.app_env,
        )
        return _lf
    except Exception:
        logger.exception("Langfuse initialization failed")
        return None


class Observation:
    def __init__(self, span=None):
        self.span = span

    def update(self, **kwargs):
        if self.span is not None:
            try:
                self.span.update(**kwargs)
            except Exception:
                logger.warning("Langfuse observation update failed", exc_info=True)


@contextmanager
def observation(name, *, as_type="span", session_id=None, **kwargs):
    client = get_langfuse()
    manager = None
    stack = ExitStack()
    span = Observation()
    if client:
        try:
            if session_id is not None:
                from langfuse import propagate_attributes

                stack.enter_context(propagate_attributes(session_id=str(session_id)))
            manager = client.start_as_current_observation(name=name, as_type=as_type, **kwargs)
            span = Observation(stack.enter_context(manager))
        except Exception:
            logger.warning("Langfuse observation start failed", exc_info=True)
    try:
        yield span
    except BaseException as exc:
        span.update(level="ERROR", status_message=type(exc).__name__)
        raise
    finally:
        try:
            stack.close()
        except Exception:
            logger.warning("Langfuse observation end failed", exc_info=True)


def traced(name, *, as_type="span", session_id=None):
    def decorate(fn):
        if inspect.isasyncgenfunction(fn):
            @wraps(fn)
            async def stream(*args, **kwargs):
                from contextlib import aclosing

                with observation(name, as_type=as_type, session_id=session_id):
                    async with aclosing(fn(*args, **kwargs)) as source:
                        async for item in source:
                            yield item
            return stream

        @wraps(fn)
        async def call(*args, **kwargs):
            with observation(name, as_type=as_type, session_id=session_id):
                return await fn(*args, **kwargs)
        return call
    return decorate


def shutdown_langfuse():
    global _lf
    client, _lf = _lf, None
    if client:
        try:
            client.flush()
            client.shutdown()
        except Exception:
            logger.warning("Langfuse shutdown failed", exc_info=True)
