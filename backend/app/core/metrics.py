"""Streaming / performance metrics: TTFT / TPOT / latency sliding-window aggregates.

简历点：可度量、可优化的流式工程——TTFT（首 Token 延迟）、TPOT（生成吞吐）、
总延迟三类指标按 endpoint 分桶滑动窗口聚合，P50/P95/P99 由 /api/metrics 暴露，
压测报告（docs/benchmark.md）直接回填这些数字。
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from app.core.config import get_settings

settings = get_settings()


@dataclass
class Sample:
    endpoint: str
    ttft_ms: float | None
    total_ms: float
    tokens: int | None
    ts: float = field(default_factory=time.monotonic)


_buckets: dict[str, deque[Sample]] = {}


def _bucket(endpoint: str) -> deque[Sample]:
    if endpoint not in _buckets:
        _buckets[endpoint] = deque(maxlen=settings.metrics_window_size)
    return _buckets[endpoint]


def record(
    endpoint: str,
    *,
    ttft_ms: float | None = None,
    total_ms: float,
    tokens: int | None = None,
) -> None:
    """记录一次请求样本（endpoint 分桶：chat / review / rag 等）。"""
    if not settings.metrics_enabled:
        return
    _bucket(endpoint).append(Sample(endpoint, ttft_ms, total_ms, tokens))


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    low, high = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    frac = k - low
    return round(sorted_vals[low] + (sorted_vals[high] - sorted_vals[low]) * frac, 1)


def snapshot() -> dict:
    """返回各 endpoint 的滑动窗口指标快照（供 /api/metrics）。"""
    out: dict = {}
    for ep, bucket in sorted(_buckets.items()):
        if not bucket:
            continue
        ttfts = sorted(s.ttft_ms for s in bucket if s.ttft_ms is not None)
        totals = sorted(s.total_ms for s in bucket)
        tokens = [s.tokens for s in bucket if s.tokens is not None]
        avg_total = sum(totals) / len(totals)
        out[ep] = {
            "count": len(bucket),
            "ttft_p50": _percentile(ttfts, 0.5),
            "ttft_p95": _percentile(ttfts, 0.95),
            "ttft_p99": _percentile(ttfts, 0.99),
            "total_p50": _percentile(totals, 0.5),
            "total_p95": _percentile(totals, 0.95),
            "total_p99": _percentile(totals, 0.99),
            "avg_tokens": round(sum(tokens) / len(tokens), 1) if tokens else 0.0,
            "tokens_per_sec": round(
                (sum(tokens) / len(tokens)) / (avg_total / 1000), 1
            )
            if tokens and avg_total > 0
            else 0.0,
        }
    return out
