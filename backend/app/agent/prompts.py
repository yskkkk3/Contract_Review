"""Prompt loader: read .md templates with {var} interpolation."""
import re
from pathlib import Path

from app.core.runtime_config import prompt_override

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_cache: dict[str, str] = {}


def load_prompt(name: str, *, contract_type_id: int | None = None, **kwargs) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if str(path) not in _cache:
        _cache[str(path)] = path.read_text(encoding="utf-8")
    override = prompt_override(name, contract_type_id)
    text = override if override is not None else _cache[str(path)]
    for key, value in kwargs.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def load_risk_dim_prompt(risk_dim: str) -> str:
    """加载风险维度细则（追加到 specialist 系统提示词）。"""
    safe = re.sub(r'[\\/:*?"<>|]', "_", risk_dim)
    path = PROMPTS_DIR / "risk_dims" / f"{safe}.md"
    override = prompt_override(f"risk_dims/{safe}")
    return override if override is not None else (path.read_text(encoding="utf-8") if path.exists() else "")


def load_chat_history_excerpt(excerpt: str) -> str:
    """Label extracted historical text without treating prior answers as legal evidence."""
    return load_prompt("chat_history_excerpt", excerpt=excerpt)
