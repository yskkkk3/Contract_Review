import re
from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


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
    prompt_name: str = Field(..., min_length=1, max_length=128)
    prompt_content: str = Field(..., min_length=1)


class PromptUpdate(BaseModel):
    prompt_name: str | None = None
    prompt_content: str | None = None
    is_active: int | None = Field(None, ge=0, le=1)

    @field_validator("*")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Prompt update fields cannot be null")
        return value


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
    model_name: str = Field(..., min_length=1, max_length=128)
    model_type: str = Field(..., pattern="^(review|chat|intent|embedding|rerank)$")
    provider: str = "siliconflow"
    api_endpoint: str = "https://api.siliconflow.cn/v1"
    api_key: str = ""
    temperature: float = Field(0.7, ge=0, le=2)
    top_p: float = Field(0.95, gt=0, le=1)
    max_tokens: int = Field(4096, ge=1, le=131072)
    is_default: int = Field(0, ge=0, le=1)

    @field_validator("api_key")
    @classmethod
    def env_reference(cls, value: str) -> str:
        if value and not re.fullmatch(r"env:[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError("Use env:VARIABLE_NAME; plaintext credentials are not stored")
        return value

    @field_validator("api_endpoint")
    @classmethod
    def endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("A credential-free HTTP(S) endpoint is required")
        return value


class ModelConfigUpdate(BaseModel):
    model_name: str | None = Field(None, min_length=1, max_length=128)
    api_endpoint: str | None = None
    api_key: str | None = None
    temperature: float | None = Field(None, ge=0, le=2)
    top_p: float | None = Field(None, gt=0, le=1)
    max_tokens: int | None = Field(None, ge=1, le=131072)
    is_default: int | None = Field(None, ge=0, le=1)
    status: str | None = Field(None, pattern="^(active|inactive)$")

    @field_validator("*")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Model update fields cannot be null")
        return value

    @field_validator("api_key", "api_endpoint")
    @classmethod
    def validate_connection(cls, value: str | None, info):
        if value is None:
            raise ValueError("Connection fields cannot be null")
        return (ModelConfigCreate.env_reference(value) if info.field_name == "api_key"
                else ModelConfigCreate.endpoint(value))


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
