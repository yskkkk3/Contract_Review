"""Request-scoped admin configuration. No process cache or persisted credentials."""
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps

from dotenv import dotenv_values
from fastapi import Depends
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal, get_db
from app.models.model_configs import ModelConfig
from app.models.prompt_manage import Prompt


@dataclass
class RuntimeConfig:
    models: dict[str, dict] = field(default_factory=dict)
    prompts: list[dict] = field(default_factory=list)


_runtime: ContextVar[RuntimeConfig | None] = ContextVar("runtime_config", default=None)
_contract_type: ContextVar[int | None] = ContextVar("prompt_contract_type", default=None)


def read_runtime(db: Session) -> RuntimeConfig:
    models = {}
    for row in db.query(ModelConfig).filter_by(status="active", is_default=1).order_by(ModelConfig.id.desc()):
        models.setdefault(row.model_type, {key: getattr(row, key) for key in (
            "model_name", "api_endpoint", "api_key", "temperature", "top_p", "max_tokens",
        )})
    prompts = [{key: getattr(row, key) for key in (
        "id", "level", "contract_type_id", "base_prompt_id", "organization_id",
        "prompt_name", "prompt_content", "is_active",
    )} for row in db.query(Prompt).order_by(Prompt.id)]
    return RuntimeConfig(models, prompts)


@contextmanager
def use_runtime(config: RuntimeConfig):
    token = _runtime.set(config)
    try:
        yield config
    finally:
        _runtime.reset(token)


async def runtime_dependency(db: Session = Depends(get_db)):
    with use_runtime(read_runtime(db)):
        yield


def runtime_job(fn):
    """Use the same configuration for ingestion, evaluation and standalone MCP calls."""
    @wraps(fn)
    async def run(*args, **kwargs):
        with SessionLocal() as db:
            schema = inspect(db.get_bind())
            snapshot = (read_runtime(db) if schema.has_table("model_configs") and schema.has_table("prompts")
                        else RuntimeConfig())
        with use_runtime(snapshot):
            return await fn(*args, **kwargs)
    return run


@contextmanager
def prompt_scope(contract_type_id: int | None):
    token = _contract_type.set(contract_type_id)
    try:
        yield
    finally:
        _contract_type.reset(token)


def model_config(role: str) -> dict | None:
    snapshot = _runtime.get()
    return snapshot.models.get(role) if snapshot else None


def credential(reference: str, fallback: str) -> str:
    if not reference:
        return fallback
    if not reference.startswith("env:"):
        raise ValueError("Model credentials must reference an environment variable")
    value = environment_value(reference[4:])
    if not value:
        raise ValueError("Configured model credential environment variable is missing")
    return value


def environment_value(name: str) -> str:
    if name in os.environ:
        return os.environ[name]
    settings = get_settings()
    value = getattr(settings, name.lower(), None)
    if isinstance(value, str) and value:
        return value
    result = ""
    paths = settings.model_config.get("env_file") or ()
    if isinstance(paths, str):
        paths = (paths,)
    for path in paths:
        result = dotenv_values(path).get(name, result) or ""
    return result


def prompt_override(name: str, contract_type_id: int | None = None) -> str | None:
    snapshot = _runtime.get()
    if snapshot is None:
        return None
    scope = contract_type_id if contract_type_id is not None else _contract_type.get()
    # A child is usable only if its complete base chain is active and in scope.
    eligible = {p["id"]: p for p in snapshot.prompts if (
        p["is_active"] and p["prompt_name"] == name and p["organization_id"] is None
        and p["contract_type_id"] in (None, scope)
    )}

    def valid(row, seen):
        if row["id"] in seen:
            return False
        if row["level"] == "system":
            return row["base_prompt_id"] is None
        base = eligible.get(row["base_prompt_id"])
        expected = {"org": "system", "override": "org"}.get(row["level"])
        return bool(base and base["level"] == expected and valid(base, seen | {row["id"]}))

    candidates = [p for p in eligible.values() if valid(p, set())]
    if not candidates:
        return None
    best = max(candidates, key=lambda p: (
        p["contract_type_id"] is not None, {"system": 0, "org": 1, "override": 2}[p["level"]], p["id"],
    ))
    return best["prompt_content"]
