"""Prompt loader: read .md templates with {var} interpolation."""
import json
import re
from pathlib import Path

from app.agent.review_profiles import COMMON, active_profile
from app.core.runtime_config import prompt_override

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_cache: dict[str, str] = {}
_PROFILE_AWARE = {
    "router", "specialist_base", "gate", "gate_repair", "arbitration",
    "review_completeness", "rag_evidence_rerank",
}


def load_prompt(name: str, *, contract_type_id: int | None = None, **kwargs) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if str(path) not in _cache:
        _cache[str(path)] = path.read_text(encoding="utf-8")
    override = prompt_override(name, contract_type_id)
    text = override if override is not None else _cache[str(path)]
    for key, value in kwargs.items():
        text = text.replace("{" + key + "}", str(value))
    profile = active_profile()
    if profile is not None and name in _PROFILE_AWARE:
        checks = COMMON.checks + (profile.checks if profile is not COMMON else ())
        selected = [check for check in checks if not kwargs.get("risk_dim") or check.risk_dim == kwargs["risk_dim"]]
        text += "\n\n" + load_prompt(
            "review_scope", profile_name=profile.name,
            checklist=json.dumps([{"id": item.id, "title": item.title, "risk_dim": item.risk_dim}
                                  for item in selected], ensure_ascii=False),
        )
        specialized = f"contract_profiles/{profile.key}"
        if (PROMPTS_DIR / f"{specialized}.md").exists():
            text += "\n\n" + load_prompt(specialized)
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
