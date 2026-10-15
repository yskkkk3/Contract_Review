"""检索指标门禁（完整评测，需真实 embedding/rerank key）。

用法（CI rag-eval job，有 SILICONFLOW_API_KEY secret 时）:
  uv run python scripts/gate_metrics.py --recall5 0.6 --mrr 0.4

低于阈值 → exit 1（阻止合并）。指标口径与 scripts/eval_rag.py 一致。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.eval.golden_set import GOLDEN_SET
from app.rag.eval.retrieval_metrics import evaluate_retrieval
from app.rag.service import get_rag_service


def _matches(case_relevant: list[str], chunk_source: str, chunk_doc_id: str) -> bool:
    # 与 eval_rag.py 一致：按文档标题关键词子串判定（doc_id / source 兜底）
    return any(kw in chunk_doc_id or kw in chunk_source for kw in case_relevant)


async def run(
    recall5: float, mrr: float, ndcg: float, concurrency: int = 2, output: Path | None = None,
) -> int:
    if not 1 <= concurrency <= 8:
        raise ValueError("concurrency must be between 1 and 8")
    if output and output.exists():
        raise FileExistsError(f"Refusing to overwrite evaluation report: {output}")
    rag = get_rag_service()
    semaphore = asyncio.Semaphore(concurrency)
    completed = 0

    async def evaluate(index, case):
        nonlocal completed
        async with semaphore:
            evidence = await rag.search(case.question, risk_dim=case.risk_dim, top_k=5)
            completed += 1
            if completed % 10 == 0:
                print(f"[gate] completed {completed}/{len(GOLDEN_SET)}", flush=True)
            return {
                "id": getattr(case, "id", str(index)), "question": case.question,
                "risk_dim": case.risk_dim, "relevant_docs": case.relevant_docs,
                "retrieved": [e.chunk.doc_id for e in evidence],
            }

    try:
        await rag.ensure_ready()
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(evaluate(index, case))
                     for index, case in enumerate(GOLDEN_SET)]
        detail = [task.result() for task in tasks]
    finally:
        await rag.close()

    metrics = evaluate_retrieval(
        [(row["relevant_docs"], row["retrieved"]) for row in detail],
        k=5, matcher=lambda rel, d: any(kw in d for kw in rel),
    )
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")

    fail = False
    if metrics["recall@k"] < recall5:
        print(f"[gate] FAIL: recall@5 {metrics['recall@k']:.3f} < {recall5}")
        fail = True
    if metrics["mrr"] < mrr:
        print(f"[gate] FAIL: mrr {metrics['mrr']:.3f} < {mrr}")
        fail = True
    if metrics["ndcg@k"] < ndcg:
        print(f"[gate] FAIL: ndcg@5 {metrics['ndcg@k']:.3f} < {ndcg}")
        fail = True
    if not fail:
        print("[gate] 检索指标达标（Recall@5 / MRR / NDCG@5）")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as handle:
            json.dump({
                "top_k": 5, "case_count": len(detail), "metrics": metrics,
                "thresholds": {"recall@k": recall5, "mrr": mrr, "ndcg@k": ndcg},
                "gate_exit_code": 1 if fail else 0, "detail": detail,
            }, handle, ensure_ascii=False, indent=2)
    return 1 if fail else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recall5", type=float, default=0.6)
    parser.add_argument("--mrr", type=float, default=0.4)
    parser.add_argument("--ndcg", type=float, default=0.5)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.recall5, args.mrr, args.ndcg, args.concurrency, args.output)))
