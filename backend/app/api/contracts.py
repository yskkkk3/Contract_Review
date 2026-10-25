"""Contract file routes: upload / parse / download / delete / set type."""
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db
from app.core.runtime_config import runtime_dependency
from app.core.security import get_current_user
from app.core.storage import get_storage
from app.models.comparison import ComparisonTask
from app.models.contract import ContractFile, ContractType
from app.models.review import ReviewTask
from app.models.session_message import Session
from app.models.user import User
from app.schemas.base import GenericResponse, PageResponse
from app.schemas.contract import (
    ContractFileResponse,
    SetContractTypeRequest,
    UploadResponse,
)
from app.services.contract_type_service import resolve_contract_type
from app.services.document_parse import extract_contract_info, parse_document

router = APIRouter(prefix="/contracts", tags=["contracts"], dependencies=[Depends(runtime_dependency)])

ALLOWED_TYPES = {"pdf", "docx", "doc"}


def _save_upload(file: UploadFile, user_id: int) -> str:
    if not file.filename:
        raise HTTPException(400, "Filename required")
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {ext}")
    return get_storage().save_upload(file.file, user_id, file.filename)


@router.post("/upload", response_model=GenericResponse[UploadResponse])
async def upload_contract(
    file: UploadFile,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传并解析：抽取文本 + LLM 抽取甲乙方/金额。"""
    save_path = _save_upload(file, current_user.id)
    file_type = file.filename.rsplit(".", 1)[-1].lower()

    storage = get_storage()
    try:
        with storage.materialize(save_path, suffix=f".{file_type}") as local_path:
            content = parse_document(local_path, file_type)
        if not content.strip():
            raise HTTPException(422, "Failed to parse document text")
        content_path = storage.save_text(content, current_user.id, Path(file.filename).stem)
    except Exception:
        storage.delete(save_path)
        raise

    info = await extract_contract_info(content)
    contract_type = resolve_contract_type(db, file.filename, content)

    record = ContractFile(
        user_id=current_user.id,
        title=file.filename,
        file_type=file_type,
        file_path=save_path,
        content_path=content_path,
        parse_status="parsed",
        party_a=info["party_a"],
        party_b=info["party_b"],
        amount=float(info["amount"]) if info.get("amount") else None,
        contract_type_id=contract_type.id if contract_type else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return GenericResponse(
        data=UploadResponse(
            file_id=record.id, title=record.title, file_type=record.file_type,
            file_url=f"/api/contracts/{record.id}/download",
            party_a=record.party_a, party_b=record.party_b, amount=record.amount,
            contract_type_id=record.contract_type_id,
        )
    )


@router.post("/upload_raw", response_model=GenericResponse[UploadResponse])
async def upload_raw(
    file: UploadFile,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """仅保存不解析（比对用）。"""
    save_path = _save_upload(file, current_user.id)
    file_type = file.filename.rsplit(".", 1)[-1].lower()
    contract_type = resolve_contract_type(db, file.filename)
    record = ContractFile(
        user_id=current_user.id,
        title=file.filename,
        file_type=file_type,
        file_path=save_path,
        content_path="",
        parse_status="uploaded",
        contract_type_id=contract_type.id if contract_type else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return GenericResponse(
        data=UploadResponse(
            file_id=record.id, title=record.title, file_type=record.file_type,
            file_url=f"/api/contracts/{record.id}/download", parse_status="uploaded",
            contract_type_id=record.contract_type_id,
        )
    )


@router.get("/{file_id}/download")
async def download(
    file_id: int, db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.get(ContractFile, file_id)
    if record is None or record.user_id != current_user.id:
        raise HTTPException(404, "File not found")
    storage = get_storage()
    if not storage.exists(record.file_path):
        raise HTTPException(404, "Stored file not found")
    if record.file_path.startswith("oss://"):
        return RedirectResponse(storage.signed_download_url(record.file_path, record.title))
    return FileResponse(record.file_path, filename=record.title)


@router.delete("/{file_id}", response_model=GenericResponse)
async def delete_file(
    file_id: int, db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.get(ContractFile, file_id)
    if record is None or record.user_id != current_user.id:
        raise HTTPException(404, "File not found")
    referenced = (
        db.query(Session.id).filter(Session.file_id == file_id).first()
        or db.query(ReviewTask.id).filter(ReviewTask.file_id == file_id).first()
        or db.query(ComparisonTask.id).filter(or_(
            ComparisonTask.standard_file_id == file_id,
            ComparisonTask.comparison_file_id == file_id,
        )).first()
    )
    if referenced:
        raise HTTPException(409, "Contract is referenced by a session; delete the session first")
    paths = (record.file_path, record.content_path)
    db.delete(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Contract is still referenced") from exc
    # A rejected database deletion must never remove the only copy of a contract.
    storage = get_storage()
    for path in paths:
        try:
            storage.delete(path)
        except Exception:
            logging.getLogger(__name__).exception("Stored contract cleanup failed file_id=%s", file_id)
    return GenericResponse(msg="file deleted")


@router.post("/{file_id}/type", response_model=GenericResponse)
async def set_contract_type(
    file_id: int, request: SetContractTypeRequest,
    db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    record = db.get(ContractFile, file_id)
    if record is None or record.user_id != current_user.id:
        raise HTTPException(404, "File not found")
    contract_type = db.get(ContractType, request.contract_type_id)
    if contract_type is None or not contract_type.is_active:
        raise HTTPException(400, "Contract type is unavailable")
    record.contract_type_id = request.contract_type_id
    record.review_position = request.review_position
    db.commit()
    return GenericResponse(msg="contract type set")


@router.get("/search", response_model=GenericResponse[PageResponse[ContractFileResponse]])
async def search_files(
    title: str | None = None,
    party: str | None = None,
    contract_type_id: int | None = Query(
        default=None,
        ge=0,
        description="合同类型 ID；0 表示未分类",
    ),
    parse_status: str | None = None,
    amount_min: float | None = Query(default=None, ge=0),
    amount_max: float | None = Query(default=None, ge=0),
    created_from: date | None = None,
    created_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按合同属性组合查询当前用户的合同，并在数据库侧分页。"""
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        raise HTTPException(422, "Minimum amount cannot exceed maximum amount")
    if created_from is not None and created_to is not None and created_from > created_to:
        raise HTTPException(422, "Start date cannot exceed end date")

    query = db.query(ContractFile).filter(ContractFile.user_id == current_user.id)
    if normalized_title := (title or "").strip():
        query = query.filter(ContractFile.title.contains(normalized_title, autoescape=True))
    if normalized_party := (party or "").strip():
        query = query.filter(
            or_(
                ContractFile.party_a.contains(normalized_party, autoescape=True),
                ContractFile.party_b.contains(normalized_party, autoescape=True),
            )
        )
    if contract_type_id == 0:
        query = query.filter(ContractFile.contract_type_id.is_(None))
    elif contract_type_id is not None:
        query = query.filter(ContractFile.contract_type_id == contract_type_id)
    if normalized_status := (parse_status or "").strip():
        query = query.filter(ContractFile.parse_status == normalized_status)
    if amount_min is not None:
        query = query.filter(ContractFile.amount >= amount_min)
    if amount_max is not None:
        query = query.filter(ContractFile.amount <= amount_max)
    if created_from is not None:
        query = query.filter(ContractFile.created_at >= datetime.combine(created_from, time.min))
    if created_to is not None:
        next_day = created_to + timedelta(days=1)
        query = query.filter(ContractFile.created_at < datetime.combine(next_day, time.min))

    total = query.count()
    records = (
        query.order_by(ContractFile.created_at.desc(), ContractFile.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return GenericResponse(
        data=PageResponse(
            items=[_to_response(record) for record in records],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("", response_model=GenericResponse[list[ContractFileResponse]])
async def list_files(
    db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    records = (
        db.query(ContractFile)
        .filter(ContractFile.user_id == current_user.id)
        .order_by(ContractFile.created_at.desc())
        .all()
    )
    return GenericResponse(data=[_to_response(r) for r in records])


def _to_response(r: ContractFile) -> ContractFileResponse:
    return ContractFileResponse(
        id=r.id, title=r.title, file_type=r.file_type, parse_status=r.parse_status,
        party_a=r.party_a, party_b=r.party_b,
        amount=r.amount, contract_type_id=r.contract_type_id, review_position=r.review_position,
        is_accepted=r.is_accepted, created_at=str(r.created_at),
    )
