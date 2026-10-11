"""Golden set 轻量门禁（无 LLM / 无 key 可跑，CI 默认执行）。

校验：id 唯一、必填字段非空、risk_dim 合法、relevant_docs 非空；
任何一条不满足 → exit 1（阻止合并/推送）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.state import RISK_DIMS
from app.rag.eval.golden_set import GOLDEN_SET

KNOWN_RISK_DIMS = set(RISK_DIMS) | {""}


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

    if errors:
        print("[gate] GOLDEN_SET 校验失败：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"[gate] GOLDEN_SET 校验通过：{len(GOLDEN_SET)} 条（id 唯一、字段完整、维度合法）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
