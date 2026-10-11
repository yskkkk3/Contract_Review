"""Query expansion (Multi-Query) for broader recall.

简历点：Multi-Query 查询改写——LLM 将用户查询改写成同义 / 拆分子问题 /
术语扩展等多个检索变体，多路召回合并去重，缓解单查询 embedding 的语义
盲区；改写失败时按规则降级为原始查询，不影响主链路；进程内 TTL 缓存
避免评测与高频场景重复调用 LLM。
"""
import json
import logging
import time
from collections import OrderedDict

from app.core.config import get_settings
from app.rag.client import get_sf_client

logger = logging.getLogger(__name__)
settings = get_settings()

_EXPAND_SYSTEM_PROMPT = """你是采购合同审阅领域的检索查询改写助手。给定用户的原始查询，生成 {n} 个检索变体，要求：
1. 从"同义改写、拆分子问题、专业术语扩展"三个角度各写一版，彼此互补、不重复；
2. 保持原查询核心语义，不添加原文没有的事实；
3. 只输出 JSON 字符串数组，例如 ["变体1", "变体2"]，不要任何解释文字。"""


class _TTLCache:
    """进程内 TTL 缓存：同一查询的改写结果复用，避免重复打 LLM。"""

    def __init__(self, ttl: float = 600.0, maxsize: int = 512) -> None:
        self._ttl = ttl
        self._maxsize = maxsize
        self._data: OrderedDict[str, tuple[float, list[str]]] = OrderedDict()

    def get(self, key: str) -> list[str] | None:
        item = self._data.get(key)
        if item is None:
            return None
        expire_at, value = item
        if time.monotonic() > expire_at:
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: list[str]) -> None:
        self._data[key] = (time.monotonic() + self._ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)


_cache = _TTLCache()


async def expand_query(query: str, variants: int | None = None) -> list[str]:
    """返回 [原查询, *改写变体]（共 min(variants,1)+1 个查询）；任何失败降级为 [query]。"""
    variants = variants or settings.rag_query_variants
    if variants <= 1 or not query.strip():
        return [query]

    cached = _cache.get(query)
    if cached is not None:
        return cached

    try:
        sf = get_sf_client()
        raw = await sf.chat(
            messages=[
                {"role": "system", "content": _EXPAND_SYSTEM_PROMPT.format(n=variants - 1)},
                {"role": "user", "content": query},
            ],
            model=settings.llm_intent_model,  # 轻量模型即可
            temperature=0.2,
            max_tokens=512,
        )
        extra = _parse_variants(raw, limit=variants - 1)
        result = [query, *extra]
        _cache.set(query, result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("query expansion failed, fallback to raw query: %s", exc)
        return [query]


def _parse_variants(raw: str, limit: int) -> list[str]:
    """容错解析：剥离 markdown 围栏与前后缀，取首个 JSON 数组；失败返回空。"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        items = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    cleaned: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip() and item.strip() not in cleaned:
            cleaned.append(item.strip())
        if len(cleaned) >= limit:
            break
    return cleaned
