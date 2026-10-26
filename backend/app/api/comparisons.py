"""Compare DOCX blocks and the stored text of parsed PDF/DOC contracts."""
import json
from difflib import SequenceMatcher
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from fastapi import APIRouter, Depends, HTTPException
from lxml.etree import XMLSyntaxError
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db
from app.core.security import get_current_user
from app.core.storage import Storage, get_storage
from app.models.comparison import ComparisonTask
from app.models.contract import ContractFile
from app.models.session_message import Session, SessionTypeEnum
from app.models.user import User
from app.schemas.base import GenericResponse
from app.schemas.comparison import (
    CharDiff,
    ComparisonResponse,
    ComparisonStartRequest,
    DiffSummary,
    FileInfo,
    ParagraphDiff,
)

router = APIRouter(prefix="/comparisons", tags=["comparisons"])


def _docx_paragraphs(path: str) -> list[str]:
    doc = Document(path)

    def blocks(container):
        for block in container.iter_inner_content():
            if isinstance(block, Paragraph):
                if block.text.strip():
                    yield block.text
            elif isinstance(block, Table):
                for row in block.rows:
                    # Merged cells can appear more than once in row.cells.
                    seen = set()
                    for cell in row.cells:
                        if cell._tc in seen:
                            continue
                        seen.add(cell._tc)
                        yield "[单元格] " + "\n".join(blocks(cell))

    return list(blocks(doc))


def _char_diff(a: str, b: str) -> list[CharDiff]:
    sm = SequenceMatcher(None, a, b)
    out: list[CharDiff] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append(CharDiff(operation="equal", std_text=a[i1:i2], cmp_text=b[j1:j2]))
        elif tag == "replace":
            out.append(CharDiff(operation="replace", std_text=a[i1:i2], cmp_text=b[j1:j2]))
        elif tag == "insert":
            out.append(CharDiff(operation="insert", std_text="", cmp_text=b[j1:j2]))
        elif tag == "delete":
            out.append(CharDiff(operation="delete", std_text=a[i1:i2], cmp_text=""))
    return out


def _comparison_paragraphs(contract: ContractFile, storage: Storage) -> list[str]:
    kind = contract.file_type.strip().lower().lstrip(".")
    if kind not in {"docx", "pdf", "doc"}:
        raise HTTPException(400, "支持 DOCX 及已解析的 PDF、DOC 合同比对")
    if kind == "docx":
        if not storage.exists(contract.file_path):
            raise HTTPException(404, f"合同“{contract.title}”的文件不存在，请重新上传")
        try:
            with storage.materialize(contract.file_path, suffix=".docx") as path:
                paragraphs = _docx_paragraphs(path)
        except (BadZipFile, PackageNotFoundError, XMLSyntaxError, ValueError) as exc:
            raise HTTPException(422, f"合同“{contract.title}”无法读取，请检查 DOCX 文件后重新上传") from exc
    else:
        if contract.parse_status != "parsed" or not contract.content_path:
            raise HTTPException(422, f"合同“{contract.title}”尚未解析，请先到合同管理上传并解析")
        if not storage.exists(contract.content_path):
            raise HTTPException(404, f"合同“{contract.title}”的解析正文不存在，请重新上传解析")
        try:
            content = storage.read_text(contract.content_path)
        except UnicodeError as exc:
            raise HTTPException(422, f"合同“{contract.title}”的正文无法读取，请重新上传解析") from exc
        paragraphs = [line.strip() for line in content.splitlines() if line.strip()]
    if not paragraphs:
        raise HTTPException(422, f"合同“{contract.title}”没有可比对的正文，请重新上传解析")
    return paragraphs


def _diff_docs(std_path: str, cmp_path: str) -> tuple[DiffSummary, list[ParagraphDiff]]:
    return _diff_paragraphs(_docx_paragraphs(std_path), _docx_paragraphs(cmp_path))


def _diff_paragraphs(std: list[str], cmp: list[str]) -> tuple[DiffSummary, list[ParagraphDiff]]:
    sm = SequenceMatcher(None, std, cmp)
    diffs: list[ParagraphDiff] = []
    diff_count = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for idx in range(i1, i2):
                diffs.append(
                    ParagraphDiff(
                        operation="equal", std_index=idx, cmp_index=j1 + idx - i1,
                        standard_text=std[idx], comparison_text=cmp[j1 + idx - i1],
                    )
                )
        else:
            diff_count += 1
            for idx in range(i1, i2):
                j_idx = j1 + (idx - i1) if j1 + idx - i1 < j2 else None
                cmp_text = cmp[j_idx] if j_idx is not None and j_idx < len(cmp) else ""
                diffs.append(
                    ParagraphDiff(
                        operation=tag, std_index=idx, cmp_index=j_idx,
                        standard_text=std[idx], comparison_text=cmp_text,
                        char_diff=_char_diff(std[idx], cmp_text),
                    )
                )
            for jdx in range(j1, j2):
                if jdx >= len(cmp):
                    continue
                i_idx = i1 + (jdx - j1) if i1 < i2 else None
                if i_idx is not None and i_idx < i2 and i_idx < len(std):
                    continue
                diffs.append(
                    ParagraphDiff(
                        operation=tag, cmp_index=jdx, comparison_text=cmp[jdx],
                    )
                )
    summary = DiffSummary(
        standard_paragraphs=len(std),
        comparison_paragraphs=len(cmp),
        difference_count=diff_count,
    )
    return summary, diffs


@router.post("", response_model=GenericResponse[ComparisonResponse])
async def start_comparison(
    request: ComparisonStartRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    std = db.get(ContractFile, request.standard_file_id)
    cmp = db.get(ContractFile, request.comparison_file_id)
    if std is None or cmp is None or std.user_id != current_user.id or cmp.user_id != current_user.id:
        raise HTTPException(404, "File not found")
    session = None
    if request.session_id:
        session = db.get(Session, request.session_id)
        if session is None or session.user_id != current_user.id or session.session_type != SessionTypeEnum.COMPARE:
            raise HTTPException(404, "Session not found")
    storage = get_storage()
    summary, diffs = _diff_paragraphs(
        _comparison_paragraphs(std, storage), _comparison_paragraphs(cmp, storage),
    )
    if session is None:
        session = Session(
            user_id=current_user.id,
            title=request.title or f"{std.title} VS {cmp.title}",
            session_type=SessionTypeEnum.COMPARE,
            file_id=std.id,
        )
        db.add(session)
        db.flush()
    session_id = session.id
    task = db.query(ComparisonTask).filter(ComparisonTask.session_id == session_id).first()
    if task is None:
        task = ComparisonTask(
            session_id=session_id, user_id=current_user.id,
            standard_file_id=std.id, comparison_file_id=cmp.id,
        )
        db.add(task)
    task.diff_summary = json.dumps(summary.model_dump(), ensure_ascii=False)
    task.standard_file_id = std.id
    task.comparison_file_id = cmp.id
    session.file_id = std.id
    task.diff_result = json.dumps([d.model_dump() for d in diffs], ensure_ascii=False)
    db.commit()
    db.refresh(task)

    return GenericResponse(
        data=ComparisonResponse(
            task_id=task.id, session_id=session_id, diff_summary=summary, diffs=diffs,
            standard_file=FileInfo(file_id=std.id, title=std.title, file_type=std.file_type,
                                   download_url=f"/api/contracts/{std.id}/download"),
            comparison_file=FileInfo(file_id=cmp.id, title=cmp.title, file_type=cmp.file_type,
                                     download_url=f"/api/contracts/{cmp.id}/download"),
        )
    )
