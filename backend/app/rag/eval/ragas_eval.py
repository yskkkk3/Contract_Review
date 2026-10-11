"""RAGAS evaluation: faithfulness / answer relevancy / context precision / context recall.

需要 ragas 依赖（optional extra: eval）。运行入口见 scripts/eval_rag.py。
"""
from __future__ import annotations


def build_ragas_dataset(
    cases: list[dict],
) -> list[dict]:
    """把 golden set 转换为 RAGAS 输入格式。

    case: {question, answer, contexts: [chunk_text], ground_truth}
    """
    return [
        {
            "user_input": c["question"],
            "response": c["answer"],
            "retrieved_contexts": c["contexts"],
            "reference": c["ground_truth"],
        }
        for c in cases
    ]


async def run_ragas_eval(dataset: list[dict], llm_model: str | None = None) -> dict:
    """执行 RAGAS 四指标评估（LLM-as-judge）。"""
    import ragas.evaluation as ragas_eval_mod
    from langchain_openai import OpenAIEmbeddings as LCOpenAIEmbeddings
    from openai import OpenAI
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.embeddings import OpenAIEmbeddings as RagasOpenAIEmbeddings
    from ragas.llms import llm_factory
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    from app.core.config import get_settings

    settings = get_settings()
    llm_client = OpenAI(
        base_url=settings.effective_llm_base_url,
        api_key=settings.effective_llm_api_key,
    )
    embedding_client = OpenAI(
        base_url=settings.effective_embedding_base_url,
        api_key=settings.effective_embedding_api_key,
    )
    # ragas 0.4 官方推荐：llm_factory + metric 实例绑定
    llm = llm_factory(llm_model or settings.llm_chat_model, client=llm_client)
    modern_emb = RagasOpenAIEmbeddings(
        client=embedding_client,
        model=settings.embedding_model,
    )
    # AnswerRelevancy 依赖 embed_query（ragas 0.4.3 新 embeddings 未提供），用 langchain wrapper
    legacy_emb = LangchainEmbeddingsWrapper(
        LCOpenAIEmbeddings(
            base_url=settings.effective_embedding_base_url,
            api_key=settings.effective_embedding_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    )
    for m in (faithfulness, context_precision, context_recall):
        m.llm = llm
    answer_relevancy.llm = llm
    answer_relevancy.embeddings = legacy_emb
    ragas_eval_mod.embedding_factory = lambda *args, **kwargs: modern_emb
    eval_dataset = EvaluationDataset.from_list(dataset)
    result = evaluate(
        dataset=eval_dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=llm,
        embeddings=modern_emb,
    )
    return result.to_pandas().to_dict(orient="records")
