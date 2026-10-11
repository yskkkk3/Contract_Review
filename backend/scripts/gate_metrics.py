"""检索指标门禁（完整评测，需真实 embedding/rerank key）。

用法（CI rag-eval job，有 SILICONFLOW_API_KEY secret 时）:
  uv run python scripts/gate_metrics.py --recall5 0.6 --mrr 0.4

低于阈值 → exit 1（阻止合并）。指标口径与 scripts/eval_rag.py 一致。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.eval.golden_set import GOLDEN_SET
from app.rag.eval.retrieval_metrics import evaluate_retrieval
from app.rag.service import get_rag_service


def _matches(case_relevant: list[str], chunk_source: str, chunk_doc_id: str) -> bool:
    # 与 eval_rag.py 一致：按文档标题关键词子串判定（doc_id / source 兜底）
    return any(kw in chunk_doc_id or kw in chunk_source for kw in case_relevant)


async def run(recall5: float, mrr: float, ndcg: float) -> int:
    rag = get_rag_service()
    await rag.ensure_ready()

    cases = []
    for case in GOLDEN_SET:
        evidence = await rag.search(case.question, risk_dim=case.risk_dim, top_k=5)
        retrieved = [e.chunk.doc_id for e in evidence]
        cases.append((case.relevant_docs, retrieved))

    metrics = evaluate_retrieval(
        cases, k=5, matcher=lambda rel, d: any(kw in d for kw in rel)
    )
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")
    await rag.close()

    fail = False
    if metrics["recall@5"] < recall5:
        print(f"[gate] FAIL: recall@5 {metrics['recall@5']:.3f} < {recall5}")
        fail = True
    if metrics["mrr"] < mrr:
        print(f"[gate] FAIL: mrr {metrics['mrr']:.3f} < {mrr}")
        fail = True
    if metrics["ndcg@5"] < ndcg:
        print(f"[gate] FAIL: ndcg@5 {metrics['ndcg@5']:.3f} < {ndcg}")
        fail = True
    if not fail:
        print("[gate] 检索指标达标（Recall@5 / MRR / NDCG@5）")
    return 1 if fail else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recall5", type=float, default=0.6)
    parser.add_argument("--mrr", type=float, default=0.4)
    parser.add_argument("--ndcg", type=float, default=0.5)
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.recall5, args.mrr, args.ndcg)))
