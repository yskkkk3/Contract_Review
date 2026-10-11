"""Prompt loader: read .md templates with {var} interpolation."""
import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_cache: dict[str, str] = {}


def load_prompt(name: str, **kwargs) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if str(path) not in _cache:
        _cache[str(path)] = path.read_text(encoding="utf-8")
    text = _cache[str(path)]
    for key, value in kwargs.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def load_risk_dim_prompt(risk_dim: str) -> str:
    """加载风险维度细则（追加到 specialist 系统提示词）。"""
    safe = re.sub(r'[\\/:*?"<>|]', "_", risk_dim)
    path = PROMPTS_DIR / "risk_dims" / f"{safe}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""
