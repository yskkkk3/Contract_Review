"""知识库构建脚本：采集语料 → chunk → Qdrant(dense) + BM25(pickle)。

用法: uv run python scripts/ingest_kb.py
产出:
  - Qdrant collections: kb_regulations / kb_institution / kb_templates
  - data/kb_bm25.pkl（BM25 索引）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.qdrant import create_qdrant_client
from app.core.runtime_config import runtime_job
from app.rag.ingest.chunker import chunk_document
from app.rag.ingest.corpus import load_corpus
from app.rag.ingest.crawler import (
    REGULATION_SAMPLES,
    TEMPLATE_SAMPLES,
    crawl_szu_pages,
)
from app.rag.ingest.loader import ensure_collection, replace_document_chunks
from app.rag.retrievers.sparse_bm25 import BM25Index

settings = get_settings()
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "kb"


def _build_docs() -> list[dict]:
    """本地语料与来源元数据；无文件时由 main 的采集/样例路径兜底。"""
    return load_corpus(DATA_DIR)


@runtime_job
async def main() -> None:
    print("[ingest] 1/4 采集语料...")
    try:
        crawled = await crawl_szu_pages()
        print(f"  采集到 {len(crawled)} 个深大制度页面")
    except Exception as exc:  # noqa: BLE001
        print(f"  网络采集失败（使用本地/内置语料）: {exc}")
        crawled = []

    docs = _build_docs()
    titles = {d["title"] for d in docs}
    for page in crawled:
        if page["title"] in titles:
            continue
        docs.append(
            {"title": page["title"], "source": page["source"], "doc_type": "institution", "text": page["text"]}
        )
        titles.add(page["title"])
    # 内置样例仅作为兜底（本地同名标题时跳过）
    for title, text in REGULATION_SAMPLES.items():
        if not any(d["title"] == title for d in docs):
            docs.append({"title": title, "source": "公开法规原文（人工整理）", "doc_type": "regulation", "text": text})
    for title, text in TEMPLATE_SAMPLES.items():
        if not any(d["title"] == title for d in docs):
            docs.append({"title": title, "source": "自建样例模板", "doc_type": "template", "text": text})

    print(f"  共 {len(docs)} 个文档")

    print("[ingest] 2/4 切分 chunk...")
    all_chunks = []
    for doc in docs:
        chunks = chunk_document(
            doc["text"], doc_id=doc["title"], source=doc["source"],
            doc_type=doc["doc_type"],
        )
        for chunk in chunks:
            chunk.meta.update(doc.get("meta", {}))
        all_chunks.extend(chunks)
    print(f"  共 {len(all_chunks)} 个 chunk")

    print("[ingest] 3/4 写入 Qdrant...")
    qdrant = create_qdrant_client(timeout=60.0)
    await ensure_collection(
        qdrant, settings.qdrant_collection_regulations, settings.embedding_dimensions
    )
    await ensure_collection(
        qdrant, settings.qdrant_collection_institution, settings.embedding_dimensions
    )
    await ensure_collection(
        qdrant, settings.qdrant_collection_templates, settings.embedding_dimensions
    )

    from collections import defaultdict

    by_type: dict[str, list] = defaultdict(list)
    for c in all_chunks:
        by_type[c.doc_type].append(c)
    collection_map = {
        "regulation": settings.qdrant_collection_regulations,
        "institution": settings.qdrant_collection_institution,
        "template": settings.qdrant_collection_templates,
    }
    total = 0
    for doc_type, chunks in by_type.items():
        coll = collection_map[doc_type]
        n = await replace_document_chunks(qdrant, coll, chunks)
        total += n
        print(f"  {doc_type} -> {coll}: {n} points")
    await qdrant.close()

    print("[ingest] 4/4 构建 BM25 索引...")
    bm25 = BM25Index()
    bm25.add_chunks(all_chunks)
    out_path = Path(settings.kb_bm25_path) if settings.kb_bm25_path else Path(settings.oss_bucket_dir).parent / "kb_bm25.pkl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bm25.save(out_path)
    print(f"  BM25 索引已保存: {out_path}")
    print(f"[ingest] 完成，共写入 {total} 个向量点")


if __name__ == "__main__":
    asyncio.run(main())
