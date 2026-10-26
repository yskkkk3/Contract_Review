"""Opt-in live acceptance on public, signed business contracts; never writes business rows.

Raw contracts/results stay in the ignored .cache directory. A model response is not
a professional pass verdict: findings require a separate evidence-based review.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import re
import sys
import time
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qdrant_client import AsyncQdrantClient
from sqlalchemy import inspect

from app.agent.graph import build_graph
from app.agent.prompts import load_prompt
from app.agent.review_profiles import get_profile, review_scope
from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.core.runtime_config import (
    RuntimeConfig,
    model_config,
    prompt_scope,
    read_runtime,
    use_runtime,
)
from app.models.contract import ContractType
from app.rag.client import LLMCircuitOpen, LLMOutputTruncated, get_sf_client, provider_status_code
from app.rag.ingest.chunker import chunk_document
from app.rag.ingest.corpus import load_corpus
from app.rag.ingest.loader import ensure_collection, upsert_chunks
from app.rag.retrievers.sparse_bm25 import BM25Index
from app.rag.service import RAGService
from app.services.document_parse import _parse_cloud_ocr
from app.services.review_service import split_contract_clauses

ROOT = Path(__file__).resolve().parents[1]
# Directory, filename prefix, authoritative type: no expected answers go to the agent.
SAMPLES = [
    ("contract_samples_20261024", "02_", "信息化项目"),
    ("contract_samples_batch3_20261024", "052_", "运维与维保"),
    ("contract_samples_batch3_20261024", "029_", "货物采购"),
    ("contract_samples_batch3_20261024", "025_", "工程建设"),
    ("contract_samples_batch3_20261024", "017_", "物业与餐饮"),
    ("contract_samples_20261024", "05_", "租赁服务"),
    ("contract_samples_batch3_20261024", "004_", "咨询与评估"),
    ("contract_samples_batch2_20261024", "08_", "检验与检测"),
    ("contract_samples_batch2_20261024", "04_", "教育与培训"),
    ("contract_samples_batch2_20261024", "07_", "法律与审计"),
    ("contract_samples_20261024", "07_", "文化与知识产权"),
    ("contract_samples_batch3_20261024", "013_", "其他服务"),
]


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def save(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def runtime_snapshot():
    engine.echo = False
    with SessionLocal() as db:
        schema = inspect(db.get_bind())
        snapshot = (read_runtime(db) if schema.has_table("model_configs")
                    and schema.has_table("prompts") else RuntimeConfig())
        type_ids = ({row.name: row.id for row in db.query(ContractType).all()}
                    if schema.has_table("contract_types") else {})
    return snapshot, type_ids


async def prepare_rag(directory: Path) -> RAGService:
    settings = get_settings()
    docs = load_corpus(ROOT / "data/kb")
    chunks = []
    for doc in docs:
        parts = chunk_document(doc["text"], doc_id=doc["title"], source=doc["source"],
                               doc_type=doc["doc_type"])
        for part in parts:
            part.meta.update(doc.get("meta", {}))
        chunks.extend(parts)
    fingerprint = digest(json.dumps([asdict(chunk) for chunk in chunks],
                                    ensure_ascii=False, sort_keys=True).encode())
    embedding = model_config("embedding") or {}
    config = {"corpus_sha256": fingerprint, "documents": len(docs), "chunks": len(chunks),
              "embedding_model": embedding.get("model_name", settings.embedding_model),
              "dimensions": settings.embedding_dimensions}
    manifest = directory / "index.json"
    qdrant = AsyncQdrantClient(path=str(directory / "vectors"))
    bm25 = BM25Index()
    bm25.add_chunks(chunks)
    rag = RAGService(qdrant=qdrant, bm25=bm25)
    if manifest.exists():
        if json.loads(manifest.read_text(encoding="utf-8")) != config:
            await rag.close()
            raise ValueError("Index inputs changed; choose a fresh acceptance directory")
    else:
        collections = {"regulation": settings.qdrant_collection_regulations,
                       "institution": settings.qdrant_collection_institution,
                       "template": settings.qdrant_collection_templates}
        for kind, collection in collections.items():
            await ensure_collection(qdrant, collection, settings.embedding_dimensions)
            selected = [c for c in chunks if c.doc_type == kind]
            await upsert_chunks(qdrant, collection, selected)
            print(f"[index] {kind}: {len(selected)}", flush=True)
        save(manifest, config)
    print(f"[index] ready: {len(docs)} documents, {len(chunks)} chunks", flush=True)
    return rag


def extract_sample(pdf: Path, output: Path) -> dict:
    import pymupdf

    cached = output.with_suffix(".text.json")
    pdf_hash = digest(pdf.read_bytes())
    if cached.exists():
        result = json.loads(cached.read_text(encoding="utf-8"))
        if result["pdf_sha256"] != pdf_hash:
            raise ValueError("Public sample changed")
        validate_material(result["text"])
        return result
    with pymupdf.open(pdf) as document:
        pages = [page.get_text() for page in document]
    complete_text = all(len(page.strip()) >= 40 for page in pages)
    settings = get_settings()
    if complete_text:
        text, method = "\n\n".join(pages), "pdf_text_all_pages"
    else:
        if len(pages) > settings.ocr_max_pages:
            raise ValueError("OCR page limit would truncate this sample")
        text, method = _parse_cloud_ocr(str(pdf)), "configured_cloud_ocr_all_pages"
    validate_material(text)
    result = {"pdf_sha256": pdf_hash, "pages": len(pages), "method": method,
              "text": text, "text_sha256": digest(text.encode())}
    save(cached, result)
    return result


def validate_material(text: str) -> None:
    """Reject known unusable outputs; this is not a guarantee of OCR fidelity."""
    if len(text.strip()) < 100:
        raise ValueError("Insufficient extracted business text")
    if len(re.findall(r"\d+,\d+,\d+,\d+,\d+", text)) >= 10:
        raise ValueError("OCR returned repeated coordinates instead of contract text")


def validate_business_material(profile_id: str, text: str) -> None:
    # Independently transcribed from the public goods PDF, page 1. This verifies
    # OCR input fidelity, not the answer expected from the contract reviewer.
    if profile_id == "goods" and not all(anchor in text for anchor in ("保修", "货到")):
        raise ValueError("Public goods sample lost visually verified warranty/payment text")


async def run(args) -> int:
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if args.extract_only:
        sem = asyncio.Semaphore(3)
        failures = []

        async def extract(folder, prefix, name):
            profile = get_profile(name)
            async with sem:
                sample = next((ROOT / "data" / folder).glob(f"{prefix}*.pdf"))
                try:
                    result = await asyncio.to_thread(extract_sample, sample, directory / profile.key)
                    validate_business_material(profile.key, result["text"])
                    print(f"[extract] {profile.key}: {result['pages']} pages, {result['method']}", flush=True)
                except Exception as exc:  # noqa: BLE001 Retain parsing failures without credentials.
                    failures.append(profile.key)
                    print(f"[extract-failure] {profile.key}: {type(exc).__name__}", flush=True)

        await asyncio.gather(*(extract(*sample) for sample in SAMPLES))
        return 1 if failures else 0
    selected = set(args.types.split(",")) if args.types else None
    available = {get_profile(sample[2]).key for sample in SAMPLES}
    if selected and not selected <= available:
        raise ValueError("Unknown profile IDs")
    snapshot, type_ids = runtime_snapshot()
    settings = get_settings()
    usage = Counter()
    incomplete = False
    sf = get_sf_client()
    original_complete = sf._complete

    async def measured_complete(role, model, **options):
        usage["chat_attempts"] += 1
        try:
            response = await original_complete(role, model, **options)
        except Exception as exc:
            if isinstance(exc, LLMOutputTruncated):
                usage["chat_successes"] += 1  # HTTP succeeded; its output is still unusable.
                usage["truncated_chat_responses"] += 1
                if exc.usage:
                    usage["prompt_tokens"] += exc.usage.prompt_tokens or 0
                    usage["completion_tokens"] += exc.usage.completion_tokens or 0
            elif isinstance(exc, LLMCircuitOpen):
                usage["circuit_rejections"] += 1
            else:
                usage[f"failed_status_{provider_status_code(exc)}"] += 1
            raise
        usage["chat_successes"] += 1
        if any(choice.finish_reason == "length" for choice in response.choices):
            usage["truncated_chat_responses"] += 1
        if response.usage:
            usage["prompt_tokens"] += response.usage.prompt_tokens or 0
            usage["completion_tokens"] += response.usage.completion_tokens or 0
        return response

    sf._complete = measured_complete
    rag = None
    with use_runtime(snapshot):
        try:
            rag = await prepare_rag(directory)
            if args.prepare_only:
                return 0
            preflight = directory / f"preflight.{args.run_id}.json"
            if preflight.exists():
                raise FileExistsError(f"Refusing to overwrite {preflight.name}")
            health = {"created_at": datetime.now(UTC).isoformat(), "passed": False,
                      "model": snapshot.models.get("review", {}).get("model_name", settings.llm_review_model)}
            try:
                response = await sf.chat_with_tools(
                    [{"role": "user", "content": load_prompt("eval_specialization_preflight")}],
                    tools=[{"type": "function", "function": {"name": "get_clause",
                           "description": "读取条款", "parameters": {"type": "object",
                           "properties": {"index": {"type": "integer"}}, "required": ["index"],
                           "additionalProperties": False}, "strict": True}}],
                    model_type="review", max_tokens=512, tool_choice="none", brief=True,
                )
                parsed = json.loads(response.content or "")
                issue = parsed.get("issue") if isinstance(parsed, dict) else None
                health["passed"] = bool(isinstance(issue, str) and "交" in issue
                                        and ("期" in issue or "时" in issue))
                if not health["passed"]:
                    health["failure_reason"] = "No valid final review JSON"
            except Exception as exc:  # noqa: BLE001 Do not spend on a batch during an outage.
                health.update(exception_type=type(exc).__name__, provider_status=provider_status_code(exc))
            save(preflight, health)
            if not health["passed"]:
                print("[blocked] Real review/tool preflight failed; business batch not started", flush=True)
                return 2
            # Make any existing RAG tool singleton use this isolated, complete index.
            import app.rag.service as service
            service._rag_service = rag
            inputs = sorted((ROOT / "app/agent").rglob("*.py"))
            inputs += sorted((ROOT / "app/agent/prompts").rglob("*.md"))
            inputs += sorted((ROOT / "app/rag").rglob("*.py"))
            hashes = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in inputs}
            graph = build_graph(rag)
            for folder, prefix, name in SAMPLES:
                profile = get_profile(name)
                if selected and profile.key not in selected:
                    continue
                output = directory / f"{profile.key}.{args.run_id}.json"
                if output.exists():
                    raise FileExistsError(f"Refusing to overwrite {output.name}")
                sample = next((ROOT / "data" / folder).glob(f"{prefix}*.pdf"))
                print(f"[sample] {profile.key}: parsing", flush=True)
                started = time.perf_counter()
                before = usage.copy()
                row = {"type": name, "profile_id": profile.key, "sample": sample.name,
                       "created_at": datetime.now(UTC).isoformat(),
                       "input_sha256": hashes, "review_model": snapshot.models.get("review", {}).get(
                           "model_name", settings.llm_review_model),
                       "professional_verdict": "pending_independent_review"}
                state = {}
                try:
                    extracted = await asyncio.to_thread(extract_sample, sample, directory / profile.key)
                    row["extraction"] = {k: v for k, v in extracted.items() if k != "text"}
                    validate_business_material(profile.key, extracted["text"])
                    chunks = split_contract_clauses(extracted["text"])
                    state = {"session_id": 0, "file_id": 0, "user_id": 0, "contract_type": name,
                             "review_scope": review_scope(name), "stance": "甲方", "intensity": "标准",
                             "description": "请审阅本合同，核对通用风险和分类专项事项。",
                             "max_concurrent": args.max_concurrent, "content_path": "", "chunks": chunks,
                             "errors": []}
                    row["chunk_count"] = len(chunks)
                    print(f"[sample] {profile.key}: {len(chunks)} chunks", flush=True)
                    with prompt_scope(type_ids.get(name)):
                        async with asyncio.timeout(args.case_timeout):
                            async for update in graph.astream(state, stream_mode="updates"):
                                for stage, values in update.items():
                                    state.update(values)
                                    print(f"[stage] {profile.key}: {stage}", flush=True)
                    row["result"] = state
                    row["execution_status"] = "incomplete" if state.get("errors") else "finished"
                except Exception as exc:  # noqa: BLE001 Retain independent sample failures.
                    row["execution_status"] = "failed"
                    row["exception_type"] = type(exc).__name__
                    row["provider_status"] = provider_status_code(exc)
                    row["partial_result"] = state
                    print(f"[failure] {profile.key}: {type(exc).__name__}", flush=True)
                row["elapsed_seconds"] = round(time.perf_counter() - started, 2)
                row["chat_usage"] = dict(usage - before)
                save(output, row)
                print(f"[saved] {output.name}: {row['execution_status']}", flush=True)
                if row["execution_status"] != "finished":
                    incomplete = True
                    if not args.keep_going:
                        print("[stop] Incomplete sample; use --keep-going for a diagnostic batch", flush=True)
                        break
                if row["chat_usage"].get("chat_attempts") and not row["chat_usage"].get("chat_successes"):
                    print("[blocked] No successful chat calls in this sample; stopping batch", flush=True)
                    break
        finally:
            if rag is not None:
                await rag.close()
            await sf.aclose()
            sf._complete = original_complete
    return 1 if incomplete else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--types", default="", help="Comma-separated profile IDs; default all 12")
    parser.add_argument("--run-id", default="initial")
    parser.add_argument("--case-timeout", type=int, default=1200)
    parser.add_argument("--max-concurrent", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--extract-only", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
