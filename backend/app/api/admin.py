"""Admin routes: contract types / prompts / model configs."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db
from app.models.contract import ContractType
from app.models.model_configs import ModelConfig
from app.models.prompt_manage import Prompt
from app.schemas.admin import (
    ContractTypeCreate,
    ContractTypeResponse,
    ContractTypeUpdate,
    ModelConfigCreate,
    ModelConfigResponse,
    ModelConfigUpdate,
    PromptCreate,
    PromptResponse,
    PromptUpdate,
)
from app.schemas.base import GenericResponse

router = APIRouter(tags=["admin"])


# ================= contract types =================
@router.get("/contract-types", response_model=GenericResponse[list[ContractTypeResponse]])
async def list_contract_types(db: DBSession = Depends(get_db)):
    items = db.query(ContractType).all()
    return GenericResponse(data=[_ct_to_resp(t) for t in items])


@router.post("/contract-types", response_model=GenericResponse[ContractTypeResponse])
async def create_contract_type(request: ContractTypeCreate, db: DBSession = Depends(get_db)):
    if db.query(ContractType).filter(ContractType.name == request.name).first():
        raise HTTPException(400, "Contract type already exists")
    item = ContractType(name=request.name, description=request.description)
    db.add(item)
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_ct_to_resp(item))


@router.put("/contract-types/{type_id}", response_model=GenericResponse[ContractTypeResponse])
async def update_contract_type(
    type_id: int, request: ContractTypeUpdate, db: DBSession = Depends(get_db)
):
    item = db.get(ContractType, type_id)
    if item is None:
        raise HTTPException(404, "Contract type not found")
    if request.name is not None:
        item.name = request.name
    if request.description is not None:
        item.description = request.description
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_ct_to_resp(item))


@router.post("/contract-types/{type_id}/activate", response_model=GenericResponse[ContractTypeResponse])
async def activate_contract_type(type_id: int, is_active: int = 1, db: DBSession = Depends(get_db)):
    item = db.get(ContractType, type_id)
    if item is None:
        raise HTTPException(404, "Contract type not found")
    item.is_active = 1 if is_active else 0
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_ct_to_resp(item))


# ================= prompts =================
@router.get("/prompts", response_model=GenericResponse[list[PromptResponse]])
async def list_prompts(level: str | None = None, db: DBSession = Depends(get_db)):
    q = db.query(Prompt)
    if level:
        q = q.filter(Prompt.level == level)
    items = q.order_by(Prompt.id).all()
    return GenericResponse(data=[_p_to_resp(p) for p in items])


@router.post("/prompts", response_model=GenericResponse[PromptResponse])
async def create_prompt(request: PromptCreate, db: DBSession = Depends(get_db)):
    item = Prompt(**request.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_p_to_resp(item))


@router.put("/prompts/{prompt_id}", response_model=GenericResponse[PromptResponse])
async def update_prompt(
    prompt_id: int, request: PromptUpdate, db: DBSession = Depends(get_db)
):
    item = db.get(Prompt, prompt_id)
    if item is None:
        raise HTTPException(404, "Prompt not found")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_p_to_resp(item))


@router.delete("/prompts/{prompt_id}", response_model=GenericResponse)
async def delete_prompt(prompt_id: int, db: DBSession = Depends(get_db)):
    item = db.get(Prompt, prompt_id)
    if item is None:
        raise HTTPException(404, "Prompt not found")
    db.delete(item)
    db.commit()
    return GenericResponse(msg="prompt deleted")


# ================= model configs =================
@router.get("/model-configs", response_model=GenericResponse[list[ModelConfigResponse]])
async def list_model_configs(model_type: str | None = None, db: DBSession = Depends(get_db)):
    q = db.query(ModelConfig)
    if model_type:
        q = q.filter(ModelConfig.model_type == model_type)
    items = q.all()
    return GenericResponse(data=[_m_to_resp(m) for m in items])


@router.post("/model-configs", response_model=GenericResponse[ModelConfigResponse])
async def create_model_config(request: ModelConfigCreate, db: DBSession = Depends(get_db)):
    item = ModelConfig(**request.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_m_to_resp(item))


@router.put("/model-configs/{model_id}", response_model=GenericResponse[ModelConfigResponse])
async def update_model_config(
    model_id: int, request: ModelConfigUpdate, db: DBSession = Depends(get_db)
):
    item = db.get(ModelConfig, model_id)
    if item is None:
        raise HTTPException(404, "Model config not found")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_m_to_resp(item))


@router.delete("/model-configs/{model_id}", response_model=GenericResponse)
async def delete_model_config(model_id: int, db: DBSession = Depends(get_db)):
    item = db.get(ModelConfig, model_id)
    if item is None:
        raise HTTPException(404, "Model config not found")
    db.delete(item)
    db.commit()
    return GenericResponse(msg="model config deleted")


def _ct_to_resp(t: ContractType) -> ContractTypeResponse:
    return ContractTypeResponse(id=t.id, name=t.name, description=t.description, is_active=t.is_active)


def _p_to_resp(p: Prompt) -> PromptResponse:
    return PromptResponse(
        id=p.id, level=p.level, contract_type_id=p.contract_type_id,
        base_prompt_id=p.base_prompt_id, organization_id=p.organization_id,
        prompt_name=p.prompt_name, prompt_content=p.prompt_content, is_active=p.is_active,
    )


def _m_to_resp(m: ModelConfig) -> ModelConfigResponse:
    return ModelConfigResponse(
        id=m.id, model_name=m.model_name, model_type=m.model_type, provider=m.provider,
        api_endpoint=m.api_endpoint, temperature=m.temperature, top_p=m.top_p,
        max_tokens=m.max_tokens, is_default=m.is_default, status=m.status,
        create_time=m.created_at, update_time=m.update_time,
    )
