"""Golden set 轻量门禁（无 LLM / 无 key 可跑，CI 默认执行）。

校验：id 唯一、必填字段非空、risk_dim 合法、relevant_docs 非空；
任何一条不满足 → exit 1（阻止合并/推送）。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.state import RISK_DIMS
from app.rag.eval.critical_cases import CRITICAL_CASES
from app.rag.eval.golden_set import GOLDEN_SET
from app.rag.ingest.corpus import load_corpus
from scripts.check_critical import check_critical

KNOWN_RISK_DIMS = set(RISK_DIMS) | {""}
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "kb"


def check_corpus(data_dir: Path) -> list[str]:
    """新增已标注语料必须有可追溯来源，并至少有一个精确标题 qrel。"""
    import json

    errors: list[str] = []
    manifest = data_dir / "sources.json"
    if not manifest.exists():
        return ["缺少来源清单 sources.json"]
    try:
        sources = json.loads(manifest.read_text(encoding="utf-8"))
        docs = {doc["title"]: doc for doc in load_corpus(data_dir)}
    except (OSError, ValueError) as exc:
        return [f"来源清单或语料无法读取: {exc}"]
    required = {
        "source", "law_name", "legal_level", "version", "effective_date",
        "verified_at", "articles", "scope", "content_kind",
    }
    qrels = {title for case in GOLDEN_SET for title in case.relevant_docs}
    qrels.update(title for case in CRITICAL_CASES for title in case.required_docs)
    for relative, metadata in sources.items():
        path = (data_dir / relative).resolve()
        if not path.is_relative_to(data_dir.resolve()) or not path.is_file() or path.suffix != ".txt":
            errors.append(f"非法或不存在的来源文件: {relative}")
            continue
        if missing := required - {key for key, value in metadata.items() if value}:
            errors.append(f"{relative}: 缺少元数据 {sorted(missing)}")
        url = urlparse(metadata.get("source", ""))
        if url.scheme != "https" or not (url.hostname or "").endswith(".gov.cn"):
            errors.append(f"{relative}: source 须指向官方 HTTPS 页面")
        for key in ("effective_date", "verified_at"):
            try:
                date.fromisoformat(metadata.get(key, ""))
            except ValueError:
                errors.append(f"{relative}: {key} 须为 ISO 日期")
        if path.stem not in qrels:
            errors.append(f"{relative}: 尚无精确标题相关性标注")
        if path.stem not in docs or not docs[path.stem]["text"].strip():
            errors.append(f"{relative}: 语料为空或无法加载")
    return errors


def main() -> int:
    errors: list[str] = []
    seen_ids: set[str] = set()
    if not GOLDEN_SET:
        errors.append("GOLDEN_SET 为空：至少需要一条评测用例")
    for case in GOLDEN_SET:
        if case.id in seen_ids:
            errors.append(f"重复 id: {case.id}")
        seen_ids.add(case.id)
        if not case.id or not case.question or not case.expected_answer:
            errors.append(f"{case.id or '<no-id>'}: question/expected_answer 必填")
        if not case.relevant_docs:
            errors.append(f"{case.id}: relevant_docs 至少标注一个相关文档")
        if case.risk_dim not in KNOWN_RISK_DIMS:
            errors.append(f"{case.id}: risk_dim '{case.risk_dim}' 不在已知维度集合")

    errors.extend(check_corpus(DATA_DIR))
    errors.extend(check_critical(DATA_DIR))
    if errors:
        print("[gate] GOLDEN_SET 校验失败：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"[gate] GOLDEN_SET {len(GOLDEN_SET)} 条及关键场景 {len(CRITICAL_CASES)} 条校验通过（来源、qrels、条件/例外正文及展示完整）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
