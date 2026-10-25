"""Admin routes: contract types / prompts / model configs."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.agent.prompts import PROMPTS_DIR
from app.core.db import get_db
from app.core.security import get_admin_user, get_current_user
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

router = APIRouter(tags=["admin"], dependencies=[Depends(get_current_user)])


def _validate_prompt(db, values):
    names = {str(p.relative_to(PROMPTS_DIR).with_suffix("")).replace("\\", "/") for p in PROMPTS_DIR.rglob("*.md")}
    if values["prompt_name"] not in names:
        raise HTTPException(422, "Prompt name must match a built-in template")
    if values.get("organization_id") is not None:
        raise HTTPException(422, "Organization-scoped prompts require an organization membership model")
    type_id = values.get("contract_type_id")
    if type_id is not None and db.get(ContractType, type_id) is None:
        raise HTTPException(422, "Contract type not found")
    base_id = values.get("base_prompt_id")
    if values["level"] == "system":
        if base_id is not None:
            raise HTTPException(422, "System prompts cannot have a base")
    else:
        base = db.get(Prompt, base_id) if base_id else None
        expected = "system" if values["level"] == "org" else "org"
        if (base is None or base.level != expected or base.prompt_name != values["prompt_name"]
                or base.organization_id is not None or base.contract_type_id not in (None, type_id)):
            raise HTTPException(422, "Invalid base prompt or contract scope")


def _activate_prompt(db, item):
    if item.is_active:
        query = db.query(Prompt).filter(
            Prompt.prompt_name == item.prompt_name, Prompt.level == item.level,
            Prompt.contract_type_id == item.contract_type_id,
            Prompt.organization_id == item.organization_id,
        )
        if item.id is not None:
            query = query.filter(Prompt.id != item.id)
        query.update({"is_active": 0})


@router.get("/prompt-templates", dependencies=[Depends(get_admin_user)])
async def prompt_templates():
    return GenericResponse(data=[{
        "name": str(path.relative_to(PROMPTS_DIR).with_suffix("")).replace("\\", "/"),
        "content": path.read_text(encoding="utf-8"),
    } for path in sorted(PROMPTS_DIR.rglob("*.md"))])


# ================= contract types =================
@router.get("/contract-types", response_model=GenericResponse[list[ContractTypeResponse]])
async def list_contract_types(db: DBSession = Depends(get_db)):
    items = db.query(ContractType).all()
    return GenericResponse(data=[_ct_to_resp(t) for t in items])


@router.post("/contract-types", response_model=GenericResponse[ContractTypeResponse], dependencies=[Depends(get_admin_user)])
async def create_contract_type(request: ContractTypeCreate, db: DBSession = Depends(get_db)):
    if db.query(ContractType).filter(ContractType.name == request.name).first():
        raise HTTPException(400, "Contract type already exists")
    item = ContractType(name=request.name, description=request.description)
    db.add(item)
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_ct_to_resp(item))


@router.put("/contract-types/{type_id}", response_model=GenericResponse[ContractTypeResponse], dependencies=[Depends(get_admin_user)])
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


@router.post("/contract-types/{type_id}/activate", response_model=GenericResponse[ContractTypeResponse], dependencies=[Depends(get_admin_user)])
async def activate_contract_type(type_id: int, is_active: int = 1, db: DBSession = Depends(get_db)):
    item = db.get(ContractType, type_id)
    if item is None:
        raise HTTPException(404, "Contract type not found")
    item.is_active = 1 if is_active else 0
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_ct_to_resp(item))


# ================= prompts =================
@router.get("/prompts", response_model=GenericResponse[list[PromptResponse]], dependencies=[Depends(get_admin_user)])
async def list_prompts(level: str | None = None, db: DBSession = Depends(get_db)):
    q = db.query(Prompt)
    if level:
        q = q.filter(Prompt.level == level)
    items = q.order_by(Prompt.id).all()
    return GenericResponse(data=[_p_to_resp(p) for p in items])


@router.post("/prompts", response_model=GenericResponse[PromptResponse], dependencies=[Depends(get_admin_user)])
async def create_prompt(request: PromptCreate, db: DBSession = Depends(get_db)):
    _validate_prompt(db, request.model_dump())
    item = Prompt(**request.model_dump())
    item.is_active = 1
    _activate_prompt(db, item)
    db.add(item)
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_p_to_resp(item))


@router.put("/prompts/{prompt_id}", response_model=GenericResponse[PromptResponse], dependencies=[Depends(get_admin_user)])
async def update_prompt(
    prompt_id: int, request: PromptUpdate, db: DBSession = Depends(get_db)
):
    item = db.get(Prompt, prompt_id)
    if item is None:
        raise HTTPException(404, "Prompt not found")
    if request.prompt_name and request.prompt_name != item.prompt_name and db.query(Prompt.id).filter(Prompt.base_prompt_id == item.id).first():
        raise HTTPException(409, "Update or delete derived prompts before renaming the base")
    _validate_prompt(db, {**{key: getattr(item, key) for key in (
        "level", "contract_type_id", "base_prompt_id", "organization_id", "prompt_name",
    )}, **request.model_dump(exclude_unset=True)})
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    _activate_prompt(db, item)
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_p_to_resp(item))


@router.delete("/prompts/{prompt_id}", response_model=GenericResponse, dependencies=[Depends(get_admin_user)])
async def delete_prompt(prompt_id: int, db: DBSession = Depends(get_db)):
    item = db.get(Prompt, prompt_id)
    if item is None:
        raise HTTPException(404, "Prompt not found")
    if db.query(Prompt.id).filter(Prompt.base_prompt_id == prompt_id).first():
        raise HTTPException(409, "Delete derived prompts first")
    db.delete(item)
    db.commit()
    return GenericResponse(msg="prompt deleted")


# ================= model configs =================
@router.get("/model-configs", response_model=GenericResponse[list[ModelConfigResponse]], dependencies=[Depends(get_admin_user)])
async def list_model_configs(model_type: str | None = None, db: DBSession = Depends(get_db)):
    q = db.query(ModelConfig)
    if model_type:
        q = q.filter(ModelConfig.model_type == model_type)
    items = q.all()
    return GenericResponse(data=[_m_to_resp(m) for m in items])


@router.post("/model-configs", response_model=GenericResponse[ModelConfigResponse], dependencies=[Depends(get_admin_user)])
async def create_model_config(request: ModelConfigCreate, db: DBSession = Depends(get_db)):
    if request.is_default:
        db.query(ModelConfig).filter_by(model_type=request.model_type).update({"is_default": 0})
    item = ModelConfig(**request.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_m_to_resp(item))


@router.put("/model-configs/{model_id}", response_model=GenericResponse[ModelConfigResponse], dependencies=[Depends(get_admin_user)])
async def update_model_config(
    model_id: int, request: ModelConfigUpdate, db: DBSession = Depends(get_db)
):
    item = db.get(ModelConfig, model_id)
    if item is None:
        raise HTTPException(404, "Model config not found")
    if request.is_default == 1:
        db.query(ModelConfig).filter(
            ModelConfig.model_type == item.model_type, ModelConfig.id != item.id,
        ).update({"is_default": 0})
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return GenericResponse(data=_m_to_resp(item))


@router.delete("/model-configs/{model_id}", response_model=GenericResponse, dependencies=[Depends(get_admin_user)])
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
