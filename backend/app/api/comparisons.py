"""Contract comparison routes (docx only, synchronous)."""
import json
from difflib import SequenceMatcher

from docx import Document
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db
from app.core.security import get_current_user
from app.core.storage import get_storage
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
    return [p.text for p in doc.paragraphs if p.text.strip()]


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


def _diff_docs(std_path: str, cmp_path: str) -> tuple[DiffSummary, list[ParagraphDiff]]:
    std = _docx_paragraphs(std_path)
    cmp = _docx_paragraphs(cmp_path)
    sm = SequenceMatcher(None, std, cmp)
    diffs: list[ParagraphDiff] = []
    diff_count = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for idx in range(i1, i2):
                diffs.append(
                    ParagraphDiff(
                        operation="equal", std_index=idx, cmp_index=idx,
                        standard_text=std[idx], comparison_text=std[idx],
                    )
                )
        else:
            diff_count += 1
            for idx in range(i1, i2):
                j_idx = j1 + (idx - i1) if j1 < j2 else None
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
    if std is None or cmp is None:
        raise HTTPException(404, "File not found")
    if std.file_type != "docx" or cmp.file_type != "docx":
        raise HTTPException(400, "Only docx files supported")

    if request.session_id:
        session = db.get(Session, request.session_id)
        if session is None or session.user_id != current_user.id:
            raise HTTPException(404, "Session not found")
        session_id = session.id
    else:
        session = Session(
            user_id=current_user.id,
            title=request.title or f"{std.title} VS {cmp.title}",
            session_type=SessionTypeEnum.COMPARE,
            file_id=std.id,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id

    storage = get_storage()
    with (
        storage.materialize(std.file_path, suffix=".docx") as std_path,
        storage.materialize(cmp.file_path, suffix=".docx") as cmp_path,
    ):
        summary, diffs = _diff_docs(std_path, cmp_path)
    task = db.query(ComparisonTask).filter(ComparisonTask.session_id == session_id).first()
    if task is None:
        task = ComparisonTask(
            session_id=session_id, user_id=current_user.id,
            standard_file_id=std.id, comparison_file_id=cmp.id,
        )
        db.add(task)
    task.diff_summary = json.dumps(summary.model_dump(), ensure_ascii=False)
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
