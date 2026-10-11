"""端到端冒烟：真实 LLM(SiliconFlow) + 本地 Qdrant(:memory:) + Agent 编排全链路。

验证：ingest → 混合检索 → 意图识别 → 专家并行 → 质检 → 仲裁。
用法: uv run python scripts/smoke_agent.py
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qdrant_client import AsyncQdrantClient

from app.agent.graph import build_graph
from app.agent.state import ReviewState
from app.core.config import get_settings
from app.rag.ingest.chunker import chunk_document
from app.rag.ingest.loader import ensure_collection, upsert_chunks
from app.rag.retrievers.sparse_bm25 import BM25Index
from app.rag.service import RAGService

settings = get_settings()

SAMPLE_CONTRACT = """第一条 合同标的
甲方委托乙方提供科研仪器采购代理服务，合同总金额为人民币 500,000 元。
第二条 付款方式
合同签订后 15 日内，甲方支付合同总金额的 50% 作为预付款；验收合格后支付 40%；剩余 10% 作为质保金，质保期满后 30 日内支付。
第三条 验收标准
乙方完成服务后应向甲方提交验收申请，甲方应在 10 个工作日内组织验收。
第四条 知识产权
本合同项下形成的全部工作成果的知识产权归甲方所有。
第五条 违约责任
任何一方逾期履行的，每逾期一日按合同总金额的万分之五支付违约金。
第六条 争议解决
双方发生争议应协商解决；协商不成的，提交深圳仲裁委员会仲裁。
第七条 保密
双方对合同内容负有保密义务，未经对方书面同意不得向第三方披露。
"""

SAMPLE_KB = [
    ("深大采购管理制度", "institution", "中标通知书发出之日起三十日内签订采购合同；签订补充协议或解除合同的，自签订或解除之日起十日内办理备案变更手续。合同价款应与成交金额一致。"),
    ("政府采购需求管理办法", "regulation", "合同文本应包含法定必备条款与采购需求全部内容，包括价款、验收标准、违约责任、知识产权归属、解决争议方法等。"),
    ("服务类合同模板", "template", "验收合格后十日内组织验收；质保期自验收合格之日起十二个月；付款按 30%/60%/10% 分三期。"),
]


async def main() -> None:
    t0 = time.monotonic()
    print("[smoke] 1/5 构建本地知识库（Qdrant :memory: + BM25）")
    qdrant = AsyncQdrantClient(location=":memory:", timeout=30.0)
    coll_map = {
        "regulation": settings.qdrant_collection_regulations,
        "institution": settings.qdrant_collection_institution,
        "template": settings.qdrant_collection_templates,
    }
    all_chunks = []
    by_type: dict[str, list] = {}
    for title, doc_type, text in SAMPLE_KB:
        chunks = chunk_document(text, doc_id=title, source=f"sample/{title}", doc_type=doc_type)
        all_chunks.extend(chunks)
        by_type.setdefault(doc_type, []).extend(chunks)
    for doc_type, chunks in by_type.items():
        await ensure_collection(qdrant, coll_map[doc_type])
        await upsert_chunks(qdrant, coll_map[doc_type], chunks)
    bm25 = BM25Index()
    bm25.add_chunks(all_chunks)

    rag = RAGService(qdrant=qdrant, bm25=bm25)
    await rag.ensure_ready()

    print("[smoke] 2/5 验证混合检索 + rerank")
    evidence, items = await rag.search_with_context("付款比例和质保金要求", risk_dim="财务与付款", top_k=3)
    print(f"  检索到 {len(items)} 条证据, 第一条来源: {items[0].chunk.source if items else 'N/A'}")
    print(f"  证据预览: {evidence[:80]}...")

    print("[smoke] 3/5 编译 LangGraph")
    graph = build_graph(rag)

    from app.services.review_service import split_contract_clauses

    chunks = split_contract_clauses(SAMPLE_CONTRACT)
    print(f"  合同切分为 {len(chunks)} 个条款块")

    state: ReviewState = {
        "session_id": 1,
        "file_id": 1,
        "user_id": 1,
        "contract_type": "服务",
        "stance": "甲方",
        "intensity": "标准",
        "description": "审阅付款与知识产权条款",
        "max_concurrent": 10,
        "chunks": chunks,
        "intent": "review",
        "intent_confidence": 1.0,
        "routed": [],
        "specialist_outputs": [],
        "gated": [],
        "final_risk_points": [],
        "summary": {},
        "errors": [],
    }

    print("[smoke] 4/5 运行 Agent 全流程（真实 LLM，最多 6 专家并行）")
    result = await graph.ainvoke(state)

    print(f"[smoke] 5/5 结果：{len(result.get('final_risk_points', []))} 个风险点")
    for p in result.get("final_risk_points", []):
        print(f"  #{p.get('index')} [{p.get('risk_level')}] {p.get('risk_dim')}: {p.get('risk_analysis', '')[:60]}...")
    print(f"  摘要: {result.get('summary', {}).get('summary', '')}")
    print(f"  整体风险: {result.get('summary', {}).get('overall_risk', '')}")
    print(f"[smoke] 完成，总耗时 {time.monotonic() - t0:.1f}s")
    await rag.close()


if __name__ == "__main__":
    asyncio.run(main())
