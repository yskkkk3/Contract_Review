"""Conservative, extractive history selection without an extra inference call."""
import re

from app.agent.prompts import load_chat_history_excerpt
from app.core.config import get_settings

settings = get_settings()

# Ambiguous follow-ups and broad reviews need the original conversational context.
_FULL_CONTEXT = re.compile(
    r"其他|遗漏|全面|全部|所有|补充|回顾|总结|之前|前面|刚才|上面|上述|继续|"
    r"这个|那个|这些|那些|它|第[一二三四五六七八九十\d]+[点条项]|"
    r"\b(other|anything else|review|summari[sz]e|previous|above|continue|that|those|it)\b",
    re.IGNORECASE,
)
_GENERIC_TERMS = {"合同", "风险", "条款", "问题", "建议", "是否", "可以", "哪些", "怎么"}


def _terms(text: str) -> set[str]:
    terms = set(re.findall(r"[a-zA-Z0-9]+", text.lower()))
    for segment in re.findall(r"[\u4e00-\u9fff]+", text):
        terms.update(segment[i:i + 2] for i in range(len(segment) - 1))
    return terms - _GENERIC_TERMS


def select_history(history: list[dict], query: str) -> list[dict]:
    """Keep short/broad histories intact; excerpt only old assistant explanations.

    The character budget is deliberately soft: original user facts, recent messages,
    and complete relevant paragraphs take precedence over meeting a size target.
    All stored messages remain untouched. If selection is uncertain, use full history.
    """
    budget = settings.chat_history_max_chars
    recent_count = max(2, settings.chat_history_recent_messages)
    if (budget <= 0 or len(history) <= recent_count
            or sum(len(m["content"]) for m in history) <= budget
            or _FULL_CONTEXT.search(query)):
        return history
    terms = _terms(query)
    if not terms:
        return history
    # Keep the recent window aligned to the start of a user turn.
    split = len(history) - recent_count
    while split > 0 and history[split]["role"] != "user":
        split -= 1
    selected = []
    found_relevant = False
    for message in history[:split]:
        if message["role"] != "assistant":
            selected.append(message)
            continue
        # Preserve paragraph boundaries and neighboring qualifications; no paraphrasing.
        paragraphs = re.split(r"\n\s*\n", message["content"])
        matches = {i for i, paragraph in enumerate(paragraphs) if _terms(paragraph) & terms}
        if matches:
            found_relevant = True
            indices = {neighbor for i in matches for neighbor in (i - 1, i, i + 1)
                       if 0 <= neighbor < len(paragraphs)}
            excerpt = "\n\n".join(paragraphs[i] for i in sorted(indices))
            if len(excerpt) == len(message["content"]):
                selected.append(message)
            else:
                selected.append({"role": "assistant", "content": load_chat_history_excerpt(excerpt)})
    selected.extend(history[split:])
    if not found_relevant or sum(len(m["content"]) for m in selected) > budget:
        return history
    return selected
