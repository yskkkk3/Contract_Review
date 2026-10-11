"""Retrieval quality metrics: Recall@K, Precision@K, MRR, NDCG@K.

纯函数实现，可在无 LLM 环境下单元测试。
"""
from __future__ import annotations


def _default_match(relevant: set[str], doc: str) -> bool:
    return doc in relevant


def _dedupe(docs: list[str]) -> list[str]:
    """文档级去重：同一 doc 的多个 chunk 只保留首个位置（避免撑高指标）。"""
    seen: set[str] = set()
    out: list[str] = []
    for d in docs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _matched_entries(relevant, retrieved: list[str], matcher) -> list:
    """每个相关条目最多命中一次，返回按检索顺序命中的相关条目。

    修复假指标：子串匹配下，同一相关关键词（如"政府采购法"）会被多个
    检索文档命中并独立计数，导致 hit / len(relevant) 超过 1（实测 1.055）。
    正确口径：一个相关条目只代表一个相关文档，命中数不超过相关条目数。
    """
    matched: list = []
    for entry in relevant:
        for doc in retrieved:
            if matcher([entry], doc):
                matched.append(entry)
                break
    return matched


def hit_at_k(relevant, retrieved: list[str], k: int) -> int:
    return int(any(_default_match(relevant, doc) for doc in retrieved[:k]))


def recall_at_k(relevant, retrieved: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(_matched_entries(relevant, retrieved[:k], _default_match)) / len(relevant)


def precision_at_k(relevant, retrieved: list[str], k: int) -> float:
    if k <= 0 or not retrieved:
        return 0.0
    return len(_matched_entries(relevant, retrieved[:k], _default_match)) / min(k, len(retrieved))


def mrr(relevant, retrieved: list[str]) -> float:
    for i, doc in enumerate(retrieved):
        if _default_match(relevant, doc):
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(relevant, retrieved: list[str], k: int) -> float:
    import math

    entries = _matched_entries(relevant, retrieved[:k], _default_match)
    if not entries:
        return 0.0
    # 每个命中的相关条目取其在检索序列中的首个命中位置计 DCG
    dcg = 0.0
    for entry in entries:
        for i, doc in enumerate(retrieved[:k]):
            if _default_match([entry], doc):
                dcg += 1.0 / math.log2(i + 2)
                break
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal > 0 else 0.0


def evaluate_retrieval(
    cases: list[tuple[set[str], list[str]]], k: int = 5, matcher=None
) -> dict:
    """cases: [(relevant_docs, retrieved_docs)] → 聚合指标。

    matcher(relevant, doc) -> bool：默认精确匹配；可传关键词子串匹配。
    retrieved 先做文档级去重，避免同一文档的多个 chunk 重复命中撑高指标。
    """
    global _default_match
    if matcher is not None:
        _default_match = matcher
    if not cases:
        return {"recall@k": 0.0, "precision@k": 0.0, "mrr": 0.0, "ndcg@k": 0.0, "hit@k": 0.0}
    n = len(cases)
    cases = [(r, _dedupe(ret)) for r, ret in cases]
    return {
        "recall@k": sum(recall_at_k(r, ret, k) for r, ret in cases) / n,
        "precision@k": sum(precision_at_k(r, ret, k) for r, ret in cases) / n,
        "mrr": sum(mrr(r, ret) for r, ret in cases) / n,
        "ndcg@k": sum(ndcg_at_k(r, ret, k) for r, ret in cases) / n,
        "hit@k": sum(hit_at_k(r, ret, k) for r, ret in cases) / n,
    }
