"""无网络、无模型的关键规则及条件/例外资料门禁（不代表法律结论准确率）。"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.state import RISK_DIMS
from app.rag.eval.critical_cases import CRITICAL_CASES
from app.rag.ingest.chunker import chunk_document
from app.rag.ingest.corpus import load_corpus
from app.rag.legal_coverage import (
    check_coverage,
    legal_context,
    legal_profiles,
    supplemental_evidence,
)
from app.rag.retrievers.sparse_bm25 import BM25Index


def check_critical(data_dir: Path, report: dict | None = None) -> list[str]:
    errors = []
    chunks = []
    docs = load_corpus(data_dir)
    for doc in docs:
        parts = chunk_document(doc["text"], doc["title"], doc["source"], doc["doc_type"])
        for part in parts:
            part.meta.update(doc["meta"])
        chunks.extend(parts)
    index = BM25Index()
    if chunks:
        index.add_chunks(chunks)
    profiles = legal_profiles()
    coverage = check_coverage(profiles, supplemental_evidence(profiles, index))
    errors.extend(f"关键规则缺少已核对的正文：{missing}" for missing in coverage.missing)
    seen = set()
    cases = []
    for case in CRITICAL_CASES:
        if case.id in seen or not all((case.id, case.clause, case.expected, case.prohibited, case.required_docs)):
            errors.append(f"关键场景重复或字段缺失：{case.id}")
        seen.add(case.id)
        if case.risk_dim not in RISK_DIMS:
            errors.append(f"关键场景维度非法：{case.id}")
        bundle = legal_context(case.clause, case.risk_dim, index)
        visible = {item.chunk.doc_id for item in bundle.evidence}
        if not set(case.required_docs) <= visible or bundle.coverage.missing:
            errors.append(f"关键场景的必要正文或例外未能完整展示：{case.id}")
        cases.append({"id": case.id, "risk_dim": case.risk_dim,
                      "clause": case.clause, "required_documents": list(case.required_docs),
                      "visible_documents": sorted(visible), "context_chars": len(bundle.text),
                      "facets": bundle.coverage.facets,
                      "passed": set(case.required_docs) <= visible and not bundle.coverage.missing})
    if report is not None:
        report.update({"method": "offline verified-source body delivery, not legal outcome accuracy",
                       "profile_count": len(profiles), "facet_count": len(coverage.facets),
                       "facets": coverage.facets, "case_count": len(cases), "cases": cases,
                       "source_hashes": {doc["title"]: hashlib.sha256(doc["text"].encode()).hexdigest()
                                         for doc in docs}, "errors": errors})
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {}
    errors = check_critical(Path(__file__).resolve().parents[1] / "data/kb", report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
    print(f"[critical-static] {report['case_count']} cases / {report['facet_count']} facets / {len(errors)} errors")
    sys.exit(1 if errors else 0)
