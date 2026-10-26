"""Step 3: specialty routing and retrieval hints do not replace shared evidence."""
from types import SimpleNamespace

import pytest

from app.agent.review_profiles import PROFILES, active_profile, contextual_query, profile_scope
from app.agent.state import RISK_DIMS
from app.rag.ingest.chunker import Chunk
from app.rag.retrievers.hybrid import RetrievedChunk
from app.rag.service import RAGService


@pytest.mark.parametrize("name", list(PROFILES))
async def test_all_types_keep_six_dimensions_and_schedule_specialty_checks(monkeypatch, name):
    from app.agent.nodes import router

    profile = PROFILES[name]
    chunks = [check.keywords[0] for check in profile.checks]

    async def incomplete_route(chunks):
        return {index: [RISK_DIMS[0]] for index in range(len(chunks))}

    monkeypatch.setattr(router, "_llm_route", incomplete_route)
    result = await router.router_node({"contract_type": name, "chunks": chunks})
    routes = result["routed"]
    assert {dim for route in routes for dim in route["risk_dims"]} == set(RISK_DIMS)
    for index, check in enumerate(profile.checks):
        assert check.risk_dim in routes[index]["risk_dims"]
        assert check.id in routes[index]["scope_check_ids"][check.risk_dim]
    scoped = [
        check_id
        for route in routes
        for check_ids in route["scope_check_ids"].values()
        for check_id in check_ids
    ]
    assert len(scoped) == len(set(scoped)) == len(profile.checks)
    assert set(scoped) == {check.id for check in profile.checks}


async def test_no_keyword_and_unknown_type_still_get_shared_review(monkeypatch):
    from app.agent.nodes import router

    async def no_route(chunks):
        return None

    monkeypatch.setattr(router, "_llm_route", no_route)
    result = await router.router_node({"contract_type": "自定义合同", "chunks": ["双方签署。"]})
    assert set(result["routed"][0]["risk_dims"]) == set(RISK_DIMS)
    assert result["routed"][0]["scope_dims"] == []
    assert result["routed"][0]["scope_check_ids"] == {}


def test_contextual_query_never_invents_a_buyer_identity():
    query = "交付源代码的约定"
    assert contextual_query(query) == query
    with profile_scope("信息化项目"):
        specialized = contextual_query(query)
        assert "信息化项目" in specialized and query in specialized
        assert "政府" not in specialized and "学校" not in specialized
        assert "租金" not in specialized
    with profile_scope("未知采购类型"):
        assert contextual_query(query) == query


async def test_retrieval_keeps_original_query_and_shared_sources(monkeypatch):
    from app.rag import service

    calls = []
    general = RetrievedChunk(Chunk("通用合同正文", "general", "source", "regulation"), 1)
    typed = RetrievedChunk(Chunk("软件交付材料", "software", "source", "template"), 0.5)

    async def retrieve(query, collection, **kwargs):
        calls.append((query, collection, kwargs.get("doc_type")))
        return [general, typed] if "信息化项目" in query else [general]

    async def expand(query):
        return [query]

    async def rank(query, candidates, top_k):
        return candidates[:top_k]

    monkeypatch.setattr(service, "expand_query", expand)
    monkeypatch.setattr(service, "rerank_chunks", rank)
    monkeypatch.setattr(service, "rerank_evidence", rank)
    rag = RAGService.__new__(RAGService)
    rag.retriever = SimpleNamespace(retrieve=retrieve)
    with profile_scope("信息化项目"):
        evidence = await rag.search("源代码交付", top_k=5)
    assert {item.chunk.doc_id for item in evidence} == {"general", "software"}
    assert any(query == "源代码交付" for query, _, _ in calls)
    assert any("信息化项目" in query for query, _, _ in calls)
    assert {collection for _, collection, _ in calls} == set(service._COLLECTIONS)
    assert all(doc_type is None for _, _, doc_type in calls)


async def test_legal_supplement_receives_original_fact_query(monkeypatch):
    rag = RAGService.__new__(RAGService)
    seen = []

    async def search(query, **kwargs):
        return []

    def supplement(query, *args):
        seen.append(query)
        return SimpleNamespace(text="", evidence=[])

    rag.search = search
    rag.legal_supplement = supplement
    with profile_scope("信息化项目"):
        await rag.search_with_context("本合同仅规定维护响应")
    assert seen == ["本合同仅规定维护响应"]


async def test_tools_bind_template_type_and_record_only_full_clause_reads():
    from app.agent.tools.registry import _get_clause, _lookup_template

    rag = RAGService.__new__(RAGService)
    seen = []

    async def search(query, **kwargs):
        seen.append((query, active_profile().key))
        return "template", []

    rag.search_with_context = search
    context = {"rag": rag, "contract_type": "租赁服务", "clauses": ["完整条款", "长" * 2100]}
    await _lookup_template({"contract_type": "信息化项目"}, context)
    assert seen == [("租赁服务 合同模板", "lease")]
    await _get_clause({"clause_index": 0}, context)
    await _get_clause({"clause_index": 1}, context)
    assert context["clause_reads"] == {0}
    assert active_profile() is None
