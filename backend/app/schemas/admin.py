from datetime import datetime

from pydantic import BaseModel, Field


# ---------- contract type ----------
class ContractTypeCreate(BaseModel):
    name: str
    description: str = ""


class ContractTypeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ContractTypeResponse(BaseModel):
    id: int
    name: str
    description: str = ""
    is_active: int = 1


# ---------- prompt ----------
class PromptCreate(BaseModel):
    level: str = Field(..., pattern="^(system|org|override)$")
    contract_type_id: int | None = None
    base_prompt_id: int | None = None
    organization_id: int | None = None
    prompt_name: str
    prompt_content: str


class PromptUpdate(BaseModel):
    prompt_name: str | None = None
    prompt_content: str | None = None
    is_active: int | None = None


class PromptResponse(BaseModel):
    id: int
    level: str
    contract_type_id: int | None = None
    base_prompt_id: int | None = None
    organization_id: int | None = None
    prompt_name: str
    prompt_content: str
    is_active: int = 1


# ---------- model config ----------
class ModelConfigCreate(BaseModel):
    model_name: str
    model_type: str = Field(..., pattern="^(review|chat|intent|embedding|rerank)$")
    provider: str = "siliconflow"
    api_endpoint: str = "https://api.siliconflow.cn/v1"
    api_key: str = ""
    temperature: float = 0.7
    top_p: float = 0.95
    max_tokens: int = 4096
    is_default: int = 0


class ModelConfigUpdate(BaseModel):
    model_name: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    is_default: int | None = None
    status: str | None = None


class ModelConfigResponse(BaseModel):
    id: int
    model_name: str
    model_type: str
    provider: str
    api_endpoint: str
    temperature: float
    top_p: float
    max_tokens: int
    is_default: int
    status: str
    create_time: datetime | None = None
    update_time: datetime | None = None
