"""RAG pure-function tests: chunker / BM25 / RRF / retrieval metrics."""
from app.rag.eval.retrieval_metrics import (
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from app.rag.ingest.chunker import Chunk, chunk_document
from app.rag.retrievers.hybrid import rrf_fusion
from app.rag.retrievers.sparse_bm25 import BM25Index


def test_chunk_by_section():
    text = "第一条 总则。\n这是总则内容，用于说明适用范围。\n第二条 验收。\n验收标准与方法应当明确约定。"
    chunks = chunk_document(text, doc_id="doc1", source="src", doc_type="regulation")
    assert len(chunks) == 2
    assert chunks[0].section == "第一条"
    assert chunks[1].section == "第二条"


def test_chunk_overlap_on_long_body():
    text = "第一节 条款。\n" + "内容内容内容。" * 200
    chunks = chunk_document(text, doc_id="d", source="s", doc_type="regulation", max_chars=200, overlap=50)
    assert len(chunks) > 2
    # 相邻块有 overlap（以首个块末尾文本出现在下一块开头为证）
    assert chunks[0].text[-30:] in chunks[1].text[:60]


def test_bm25_rank():
    bm25 = BM25Index()
    bm25.add_chunks([
        Chunk(text="采购合同应当明确验收标准及付款方式", doc_id="a", source="s1", doc_type="institution"),
        Chunk(text="科研项目申报与经费管理规定", doc_id="b", source="s2", doc_type="regulation"),
        Chunk(text="合同验收流程与质保期要求", doc_id="c", source="s3", doc_type="institution"),
    ])
    ranked = bm25.search("合同验收标准", top_k=2)
    assert len(ranked) >= 1
    assert ranked[0][0].doc_id == "a"  # 最相关文档排第一


def test_rrf_fusion():
    dense = [
        Chunk(text="A1", doc_id="a", source="s", doc_type="t"),
        Chunk(text="B1", doc_id="b", source="s", doc_type="t"),
    ]
    sparse = [
        Chunk(text="B1", doc_id="b", source="s", doc_type="t"),
        Chunk(text="C1", doc_id="c", source="s", doc_type="t"),
    ]
    fused = rrf_fusion(dense, sparse)
    doc_ids = [c.doc_id for c, _ in fused]
    assert doc_ids[0] == "b"  # 双路命中排最前
    assert set(doc_ids) == {"a", "b", "c"}


def test_retrieval_metrics():
    relevant = {"d1", "d2"}
    retrieved = ["d1", "x", "d2", "y"]
    assert recall_at_k(relevant, retrieved, 5) == 1.0
    assert precision_at_k(relevant, retrieved, 2) == 0.5
    assert mrr(relevant, retrieved) == 1.0
    assert ndcg_at_k(relevant, retrieved, 5) > 0.9


def test_retrieval_metrics_substring_no_inflate():
    """回归：子串匹配下同一相关关键词被多个文档命中不得让 recall 超 1。"""
    from app.rag.eval.retrieval_metrics import evaluate_retrieval

    cases = [(["政府采购法"], ["政府采购法·合同签订与验收", "政府采购法实施条例", "政府采购法·细则"])]
    m = evaluate_retrieval(cases, k=5, matcher=lambda rel, d: any(kw in d for kw in rel))
    assert m["recall@k"] <= 1.0
    assert m["ndcg@k"] <= 1.0
    assert m["hit@k"] == 1.0


def test_query_expansion_fallback():
    """回归：variants<=1 或 LLM 异常时降级为原查询，不影响主链路。"""
    import asyncio

    from app.rag.query_expansion import _parse_variants, expand_query

    assert asyncio.run(expand_query("逾期付款违约金", variants=1)) == ["逾期付款违约金"]
    # 容错解析：围栏 / 前后缀 / 非 JSON / 去重
    assert _parse_variants('```json\n["a", "b"]\n```', 2) == ["a", "b"]
    assert _parse_variants('好的，变体如下：["x", "y", "x"] 请查收', 2) == ["x", "y"]
    assert _parse_variants("无数组", 2) == []
    assert _parse_variants('{"k": 1}', 2) == []


async def test_query_expansion_timeout_does_not_block_retrieval_or_cache_failure(monkeypatch):
    import asyncio

    from app.rag import query_expansion

    class Client:
        slow = True
        calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            if self.slow:
                await asyncio.sleep(1)
            return '["采购验收起算规则"]'

    client = Client()
    monkeypatch.setattr(query_expansion, "get_sf_client", lambda: client)
    monkeypatch.setattr(query_expansion.settings, "rag_query_expansion_timeout", 0.01)
    query = "独立的改写超时回归样例"
    assert await query_expansion.expand_query(query, variants=2) == [query]
    client.slow = False
    assert await query_expansion.expand_query(query, variants=2) == [query, "采购验收起算规则"]
    assert await query_expansion.expand_query(query, variants=2) == [query, "采购验收起算规则"]
    assert client.calls == 2


def test_retrieval_metrics_empty():
    m = {"recall@k": 0.0, "precision@k": 0.0, "mrr": 0.0, "ndcg@k": 0.0, "hit@k": 0.0}
    assert evaluate_aggregate([]) == m


def evaluate_aggregate(cases):
    from app.rag.eval.retrieval_metrics import evaluate_retrieval

    return evaluate_retrieval(cases, k=5)


async def test_rerank_keeps_document_identity_for_identical_passages(monkeypatch):
    from app.rag import rerank
    from app.rag.retrievers.hybrid import RetrievedChunk

    sent = []

    class FakeClient:
        async def rerank(self, query, documents, top_n):
            sent.extend(documents)
            return [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]

    monkeypatch.setattr(rerank, "get_sf_client", FakeClient)
    candidates = [
        RetrievedChunk(Chunk("合同付款期限应明确", "国家付款规则", "source-a", "regulation", "第九条"), 0.2),
        RetrievedChunk(Chunk("合同付款期限应明确", "学校付款制度", "source-b", "institution", "第三条"), 0.1),
    ]
    ranked = await rerank.rerank_chunks("学校采购付款", candidates, top_k=2)
    assert len(set(sent)) == 2
    assert all(candidate.chunk.doc_id in passage and candidate.chunk.text in passage
               for candidate, passage in zip(candidates, sent, strict=True))
    assert [item.chunk.doc_id for item in ranked] == ["学校付款制度", "国家付款规则"]
    assert ranked[0].score == 0.9
