"""Compare uploaded PDF/DOC text and DOCX files without another model/parse call."""
import json

import pytest
from docx import Document

from app.core.db import SessionLocal
from app.models.comparison import ComparisonTask
from app.models.contract import ContractFile
from app.models.session_message import Session
from tests.test_priority_fixes import other_headers as other_headers
from tests.test_priority_fixes import user_id


@pytest.fixture()
def files(client, auth_headers, tmp_path):
    def create(kind, text, status="parsed", content=True):
        with SessionLocal() as db:
            number = db.query(ContractFile).count() + 1
            original = tmp_path / f"contract-{number}.{kind.strip('.').lower()}"
            parsed = tmp_path / f"parsed-{number}.txt"
            if kind.strip(".").lower() == "docx":
                document = Document()
                for line in text.splitlines():
                    document.add_paragraph(line)
                document.save(original)
            else:
                original.write_bytes(b"Stored original; comparison must use the parsed text")
            if content:
                parsed.write_text(text, encoding="utf-8")
            record = ContractFile(
                user_id=user_id(auth_headers), title=original.name, file_type=kind,
                file_path=str(original), content_path=str(parsed) if content else "",
                parse_status=status,
            )
            db.add(record)
            db.commit()
            return record.id
    return create


@pytest.mark.parametrize(("base_kind", "target_kind"), [
    ("pdf", "pdf"), ("doc", "doc"), ("pdf", "docx"), ("docx", "doc"), (".PDF", "DOC"),
])
def test_uploaded_contract_formats_can_be_compared(client, auth_headers, files, monkeypatch, base_kind, target_kind):
    from app.services import document_parse

    monkeypatch.setattr(document_parse, "parse_document", lambda *args: pytest.fail("Reuse the existing parsed text"))
    base = files(base_kind, "第一条 付款\n金额为100元")
    target = files(target_kind, "第一条 付款\n金额为200元")
    response = client.post("/api/comparisons", headers=auth_headers, json={
        "standard_file_id": base, "comparison_file_id": target,
    })
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["diff_summary"]["difference_count"] == 1
    changed = [point for point in data["diffs"] if point["operation"] == "replace"]
    assert changed[0]["standard_text"] == "金额为100元"
    assert changed[0]["comparison_text"] == "金额为200元"
    history = client.get(f"/api/sessions/{data['session_id']}/history", headers=auth_headers).json()["data"]
    assert history["standard_file"]["file_id"] == base
    assert history["comparison_file"]["file_id"] == target


def test_raw_docx_remains_available_without_parsing(client, auth_headers, files):
    base = files("docx", "原条款", status="uploaded", content=False)
    target = files("docx", "新条款", status="uploaded", content=False)
    response = client.post("/api/comparisons", headers=auth_headers, json={
        "standard_file_id": base, "comparison_file_id": target,
    })
    assert response.status_code == 200


@pytest.mark.parametrize(("kind", "text", "status", "content", "expected"), [
    ("pdf", "条款", "uploaded", False, 422),
    ("doc", "条款", "failed", True, 422),
    ("pdf", "条款", "parsed", False, 422),
    ("pdf", " \n\t", "parsed", True, 422),
    ("docx", "", "uploaded", False, 422),
    ("txt", "条款", "parsed", True, 400),
])
def test_unavailable_input_has_clear_error_and_creates_no_session(
    client, auth_headers, files, kind, text, status, content, expected,
):
    base = files(kind, text, status=status, content=content)
    target = files("docx", "有效条款")
    response = client.post("/api/comparisons", headers=auth_headers, json={
        "standard_file_id": base, "comparison_file_id": target,
    })
    assert response.status_code == expected
    with SessionLocal() as db:
        assert db.query(ComparisonTask).count() == 0
        assert db.query(Session).count() == 0


def test_missing_parsed_text_does_not_replace_a_previous_comparison(client, auth_headers, files):
    base = files("pdf", "金额100元")
    target = files("docx", "金额200元")
    body = {"standard_file_id": base, "comparison_file_id": target}
    saved = client.post("/api/comparisons", headers=auth_headers, json=body).json()["data"]
    with SessionLocal() as db:
        contract = db.get(ContractFile, base)
        contract.content_path += ".missing"
        db.commit()
    response = client.post("/api/comparisons", headers=auth_headers,
                           json={**body, "session_id": saved["session_id"]})
    assert response.status_code == 404
    with SessionLocal() as db:
        task = db.get(ComparisonTask, saved["task_id"])
        assert json.loads(task.diff_result) == saved["diffs"]
        assert db.query(Session).count() == 1


def test_parsed_documents_still_require_ownership(client, auth_headers, other_headers, files):
    base = files("pdf", "私有合同正文")
    target = files("doc", "私有合同正文")
    response = client.post("/api/comparisons", headers=other_headers, json={
        "standard_file_id": base, "comparison_file_id": target,
    })
    assert response.status_code == 404
    with SessionLocal() as db:
        assert db.query(ComparisonTask).count() == 0
