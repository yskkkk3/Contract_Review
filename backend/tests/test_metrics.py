"""Metrics 单元测试：滑动窗口聚合 / 百分位 / 禁用开关。"""
from __future__ import annotations

from app.core import metrics
from app.core.metrics import snapshot


def _reset():
    metrics._buckets.clear()


def test_record_and_snapshot():
    _reset()
    metrics.record("chat", ttft_ms=100.0, total_ms=500.0, tokens=50)
    metrics.record("chat", ttft_ms=300.0, total_ms=900.0, tokens=120)
    snap = snapshot()
    assert snap["chat"]["count"] == 2
    assert snap["chat"]["ttft_p50"] == 200.0  # (100+300)/2
    assert snap["chat"]["total_p95"] == 880.0  # 2 样本插值: 500+(900-500)*0.95
    assert snap["chat"]["avg_tokens"] == 85.0


def test_percentile_interpolation():
    _reset()
    for v in [10.0, 20.0, 30.0, 40.0]:
        metrics.record("chat", ttft_ms=v, total_ms=v)
    snap = snapshot()
    # 4 样本：p50 → k=1.5 → 20 + (30-20)*0.5 = 25
    assert snap["chat"]["ttft_p50"] == 25.0
    # p99 → k=2.97 → 30 + (40-30)*0.97 = 39.7
    assert snap["chat"]["ttft_p99"] == 39.7


def test_disabled_records_nothing(monkeypatch):
    monkeypatch.setattr(metrics.get_settings(), "metrics_enabled", False)
    _reset()
    metrics.record("chat", ttft_ms=1.0, total_ms=2.0)
    assert snapshot() == {}
