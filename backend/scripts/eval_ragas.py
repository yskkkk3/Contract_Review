"""RAGAS 生成质量评测（LLM-as-judge，四指标）。

用法: uv run --extra eval python scripts/eval_ragas.py [--cases 10]
流程: golden set 抽代表性子集 → RAG 检索 top_k=5 → LLM 生成回答 →
      RAGAS faithfulness / answer_relevancy / context_precision / context_recall
产出: 终端输出指标汇总（供人工回填 docs/rag-eval.md）
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.rag.client import get_sf_client
from app.rag.eval.golden_set import GOLDEN_SET
from app.rag.eval.ragas_eval import build_ragas_dataset, run_ragas_eval
from app.rag.service import get_rag_service

settings = get_settings()

# 按维度抽样的代表性 case id（覆盖全部 6 个风险维度）
REPRESENTATIVE_IDS = ["R01", "R03", "R05", "R07", "R10", "R33", "R41", "R50", "R55", "R61"]


def _pick(case_count: int) -> list:
    if case_count >= len(GOLDEN_SET):
        return GOLDEN_SET
    by_id = {c.id: c for c in GOLDEN_SET}
    picked = [by_id[i] for i in REPRESENTATIVE_IDS if i in by_id]
    # 补足到 case_count
    for case in GOLDEN_SET:
        if len(picked) >= case_count:
            break
        if case not in picked:
            picked.append(case)
    return picked[:case_count]


async def main(case_count: int) -> None:
    rag = get_rag_service()
    await rag.ensure_ready()
    sf = get_sf_client()
    cases = _pick(case_count)
    print(f"[ragas] 评测 {len(cases)} 条 golden case（RAG 检索 top_k=5 + LLM 生成回答）")

    dataset = []
    for case in cases:
        evidence = await rag.search(case.question, risk_dim=case.risk_dim, top_k=5)
        contexts = [f"[{e.chunk.doc_id}] {e.chunk.text[:800]}" for e in evidence]
        ctx_blob = "\n".join(contexts) if contexts else "（无检索结果）"
        answer = await sf.chat(
            [
                {
                    "role": "system",
                    "content": "你是高校采购合同审阅助手。仅依据以下检索到的制度/法规上下文回答，无法确定时明确说明，不编造。",
                },
                {"role": "user", "content": f"【上下文】\n{ctx_blob}\n\n【问题】{case.question}"},
            ],
            model=settings.llm_chat_model,
            temperature=0,
            max_tokens=512,
        )
        dataset.append(
            {"question": case.question, "answer": answer, "contexts": contexts, "ground_truth": case.expected_answer}
        )
        print(f"  [{case.id}] {case.question[:24]}... ctx={len(contexts)}")

    await rag.close()
    rows = await run_ragas_eval(build_ragas_dataset(dataset))
    print("\n=== RAGAS 四指标（逐条） ===")
    agg = {"faithfulness": [], "answer_relevancy": [], "context_precision": [], "context_recall": []}
    for row in rows:
        for k in agg:
            v = row.get(k)
            if isinstance(v, (int, float)) and v == v:  # 剔除 nan（空上下文导致无法评分）
                agg[k].append(float(v))
        print(
            f"  {row.get('user_input', '')[:24]:26} F={row.get('faithfulness')} "
            f"AR={row.get('answer_relevancy')} CP={row.get('context_precision')} CR={row.get('context_recall')}"
        )
    print("\n=== 均值（剔除 nan） ===")
    for k, vals in agg.items():
        mean = sum(vals) / len(vals) if vals else float("nan")
        print(f"  {k}: {mean:.3f}  (n={len(vals)})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(main(args.cases))
