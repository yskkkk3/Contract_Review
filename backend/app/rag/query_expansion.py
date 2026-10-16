"""Query expansion (Multi-Query) for broader recall.

简历点：Multi-Query 查询改写——LLM 将用户查询改写成同义 / 拆分子问题 /
术语扩展等多个检索变体，多路召回合并去重，缓解单查询 embedding 的语义
盲区；改写失败时按规则降级为原始查询，不影响主链路；进程内 TTL 缓存
避免评测与高频场景重复调用 LLM。
"""
import asyncio
import json
import logging
import time
from collections import OrderedDict

from app.agent.prompts import load_prompt
from app.core.config import get_settings
from app.rag.client import get_sf_client

logger = logging.getLogger(__name__)
settings = get_settings()

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
    """返回原查询及最多 variants-1 个互补改写；任何失败降级为原查询。"""
    variants = settings.rag_query_variants if variants is None else variants
    if variants <= 1 or not query.strip():
        return [query]

    cache_key = f"{variants}:{query}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        sf = get_sf_client()
        raw = await asyncio.wait_for(sf.chat(
            messages=[
                {"role": "system", "content": load_prompt("rag_query_expansion", n=variants - 1)},
                {"role": "user", "content": query},
            ],
            model=settings.llm_intent_model,  # 轻量模型即可
            temperature=0.2,
            max_tokens=512,
            brief=True,
        ), timeout=settings.rag_query_expansion_timeout)
        extra = _parse_variants(raw, limit=variants - 1)
        result = [query, *(item for item in extra if item != query)]
        _cache.set(cache_key, result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("query expansion failed, fallback to raw query: %s", exc)
        return [query]


def _parse_variants(raw: str, limit: int) -> list[str]:
    """容错解析：剥离 markdown 围栏与前后缀，取首个 JSON 数组；失败返回空。"""
    if limit <= 0:
        return []
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
