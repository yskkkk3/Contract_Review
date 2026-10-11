"""RAG 测评脚本：检索指标（Recall@K/MRR/NDCG）+ RAGAS 四指标。

用法: uv run --extra eval python scripts/eval_rag.py
产出: docs/rag-eval.md（由脚本汇总输出到终端，报告人工整理）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.eval.golden_set import GOLDEN_SET
from app.rag.eval.retrieval_metrics import evaluate_retrieval
from app.rag.service import get_rag_service


def _matches(case_relevant: list[str], chunk_source: str, chunk_doc_id: str) -> bool:
    # golden set 的 relevant_docs 按文档标题标注，匹配 chunk 的 doc_id（或 source 兜底）
    return any(kw in chunk_doc_id or kw in chunk_source for kw in case_relevant)


async def main() -> None:
    rag = get_rag_service()
    await rag.ensure_ready()

    print("=" * 60)
    print("RAG 检索质量评估（Recall@K / Precision@K / MRR / NDCG@K）")
    print("=" * 60)
    cases = []
    detail = []
    for case in GOLDEN_SET:
        evidence = await rag.search(case.question, risk_dim=case.risk_dim, top_k=5)
        retrieved = [e.chunk.doc_id for e in evidence]
        cases.append((case.relevant_docs, retrieved))
        detail.append(
            {"id": case.id, "question": case.question, "retrieved": retrieved[:5]}
        )
    # 匹配口径：golden set 的 relevant_docs 为文档标题关键词，按子串判定；
    # 内部做文档级去重，避免同一文档多个 chunk 重复命中虚高指标。
    metrics = evaluate_retrieval(cases, k=5, matcher=lambda rel, d: any(kw in d for kw in rel))
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")

    for d in detail[:5]:
        print(f"  [{d['id']}] {d['question'][:30]}... -> {d['retrieved'][:2]}")

    await rag.close()
    print("\nRAGAS 生成质量评估需额外运行（需 eval extra + LLM judge），见 docs/rag-eval.md 模板")


if __name__ == "__main__":
    asyncio.run(main())
