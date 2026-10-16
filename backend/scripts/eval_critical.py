"""真实审阅的关键条件回归；测试答案只给独立评审，不注入被测专家。"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.nodes.gate import gate_node
from app.agent.nodes.specialist import _run_specialist
from app.agent.prompts import load_prompt
from app.core.config import get_settings
from app.rag.client import (
    get_sf_client,
    is_provider_access_error,
    provider_error_code,
    provider_status_code,
)
from app.rag.context import assemble_context
from app.rag.eval.critical_cases import CRITICAL_CASES
from app.rag.legal_coverage import check_coverage, matching_profiles
from app.rag.service import get_rag_service

JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "passed": {"type": "boolean"},
        "missed": {"type": "array", "items": {"type": "string"}},
        "unsupported": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
    },
    "required": ["passed", "missed", "unsupported", "explanation"],
}


async def run(output: Path, concurrency: int = 2, ids: str = "") -> int:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite report: {output}")
    if not 1 <= concurrency <= 4:
        raise ValueError("concurrency must be between 1 and 4")
    selected = set(ids.split(",")) if ids else {case.id for case in CRITICAL_CASES}
    cases = [case for case in CRITICAL_CASES if case.id in selected]
    if len(cases) != len(selected):
        raise ValueError("Unknown or duplicate case ids")
    output.parent.mkdir(parents=True, exist_ok=True)
    checkpoints = output.with_suffix(".cases")
    checkpoints.mkdir(exist_ok=False)
    rag = get_rag_service()
    sf = get_sf_client()
    settings = get_settings()
    source_root = Path(__file__).resolve().parents[1]
    inputs = [*sorted((source_root / "app/agent/prompts").rglob("*.md")),
              source_root / "app/agent/nodes/specialist.py", source_root / "app/agent/nodes/gate.py",
              source_root / "app/rag/legal_coverage.py", source_root / "data/kb/legal_checks.json",
              source_root / "app/rag/client.py", source_root / "app/core/config.py"]
    inputs.append(source_root / "app/agent/rules/legal_guards.py")
    input_hashes = {path.relative_to(source_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in inputs}
    sem = asyncio.Semaphore(concurrency)
    started = time.perf_counter()
    stopped = asyncio.Event()

    async def evaluate(case):
        async with sem:
            tick = time.perf_counter()
            row = {**asdict(case), "passed": False}
            stage = "retrieval"
            try:
                if stopped.is_set():
                    raise RuntimeError("Provider unavailable; evaluation stopped")
                evidence = await rag.search(case.clause, risk_dim=case.risk_dim, top_k=3)
                baseline = assemble_context(evidence, 3000)
                profiles = matching_profiles(case.clause, case.risk_dim)
                prior = check_coverage(profiles, baseline.visible)
                bundle = rag.legal_supplement(case.clause, case.risk_dim, evidence)
                visible = {item.chunk.doc_id for item in bundle.evidence}
                row.update({
                    "retrieved_top3": [item.chunk.doc_id for item in evidence],
                    "semantic_only_3000": {"facets": prior.facets, "missing": prior.missing},
                    "supplemented": {"facets": bundle.coverage.facets,
                                     "missing": bundle.coverage.missing,
                                     "missing_documents": sorted(set(case.required_docs) - visible),
                                     "context_chars": len(bundle.text)},
                })
                state = {"stance": "甲方", "intensity": "标准", "chunks": [case.clause], "errors": []}
                row["retrieval_seconds"] = round(time.perf_counter() - tick, 2)
                stage = "specialist"
                # Only the clause and dimension are passed; expected/prohibited stay outside the agent.
                expert = await asyncio.wait_for(
                    _run_specialist(asyncio.Semaphore(1), case.clause, case.risk_dim, state, rag), 240,
                )
                if expert.get("provider_unavailable"):
                    stopped.set()
                    row["errors"] = expert["diagnostics"]
                    raise RuntimeError("Provider unavailable; evaluation stopped")
                state["specialist_outputs"] = [expert]
                state["errors"] = list(expert["diagnostics"])
                if expert["coverage_issues"]:
                    state["errors"].append("关键依据未完整展示")
                row["specialist_seconds"] = round(time.perf_counter() - tick - row["retrieval_seconds"], 2)
                stage = "gate"
                gated = await asyncio.wait_for(gate_node(state), 180)
                row.update({"initial_risk_points": expert["initial_result"],
                            "audit_status": expert["audit_status"], "pre_gate_risk_points": expert["result"],
                            "audit_unresolved": expert.get("audit_unresolved", []),
                            "final_risk_points": gated["gated"], "errors": gated["errors"],
                            "evidence_context": expert["evidence_context"]})
                row["gate_seconds"] = round(time.perf_counter() - tick - row["retrieval_seconds"] - row["specialist_seconds"], 2)
                stage = "judge"
                judge = await sf.chat_structured([
                    {"role": "system", "content": load_prompt("eval_critical")},
                    {"role": "user", "content": json.dumps({
                        "clause": case.clause, "risk_dim": case.risk_dim,
                        "expected": case.expected, "prohibited": case.prohibited,
                        "evidence_context": expert["evidence_context"],
                        "final_risk_points": gated["gated"],
                    }, ensure_ascii=False)},
                ], json_schema=JUDGE_SCHEMA, model=settings.llm_review_model,
                    temperature=0, max_tokens=4096)
                valid = (isinstance(judge, dict) and isinstance(judge.get("passed"), bool)
                         and isinstance(judge.get("missed"), list)
                         and isinstance(judge.get("unsupported"), list)
                         and isinstance(judge.get("explanation"), str))
                row["judge"] = judge
                row["passed"] = bool(valid and judge["passed"] and not judge["missed"]
                                     and not judge["unsupported"] and not gated["errors"]
                                     and not bundle.coverage.missing
                                     and not row["supplemented"]["missing_documents"])
            except Exception as exc:  # noqa: BLE001 Evaluate other cases and retain failed trace.
                if is_provider_access_error(exc):
                    stopped.set()
                if stopped.is_set():
                    row["evaluation_status"] = "blocked_provider"
                row["exception"] = type(exc).__name__
                row["failed_stage"] = stage
                row["http_status"] = provider_status_code(exc)
                row["provider_error_code"] = provider_error_code(exc)
            row["elapsed_seconds"] = round(time.perf_counter() - tick, 2)
            with (checkpoints / f"{case.id}.json").open("x", encoding="utf-8") as handle:
                json.dump(row, handle, ensure_ascii=False, indent=2)
            print(f"[critical] {case.id} {'PASS' if row['passed'] else 'FAIL'} "
                  f"{row['elapsed_seconds']}s", flush=True)
            return row

    try:
        # Fail before queueing the suite when credentials/balance are already unavailable.
        await sf.chat([{"role": "user", "content": "回复OK"}],
                      model=settings.llm_review_model, max_tokens=8, brief=True)
        await rag.ensure_ready()
        rows = await asyncio.gather(*(evaluate(case) for case in cases))
    finally:
        await rag.close()
        await sf.aclose()
    passed = sum(row["passed"] for row in rows)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "method": "model-assisted synthetic clause regression; not certified legal accuracy",
        "coverage_comparison": "same live top3 chunks: semantic-only 3000 chars vs linked verified bodies",
        "case_set_sha256": hashlib.sha256(json.dumps([asdict(c) for c in cases],
                                                    ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "input_sha256": input_hashes,
        "inference_policy": {"allowed_models": settings.llm_allowed_models,
                             "http_trust_env": settings.llm_http_trust_env,
                             "brief_disable_thinking": settings.llm_brief_disable_thinking},
        "brief_reasoning_effort": settings.llm_brief_reasoning_effort,
        "models": {"review_and_judge": settings.llm_review_model,
                   "completeness_and_gate": settings.llm_review_model},
        "case_count": len(rows), "passed": passed, "failed": len(rows) - passed,
        "evaluation_status": "blocked_provider" if stopped.is_set() else "finished",
        "elapsed_seconds": round(time.perf_counter() - started, 2), "detail": rows,
    }
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(f"[critical] passed {passed}/{len(rows)}", flush=True)
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--concurrency", default=2, type=int)
    parser.add_argument("--ids", default="", help="Comma-separated case IDs; default all critical cases")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.output, args.concurrency, args.ids)))
