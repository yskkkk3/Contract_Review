
from pydantic import BaseModel, Field


class ReviewStartRequest(BaseModel):
    session_id: int
    stance: str = Field(..., pattern="^(甲方|乙方)$")
    intensity: str = Field("标准", pattern="^(严格|标准|宽松)$")
    description: str | None = None
    contract_type: str = ""
    max_concurrent: int = Field(20, ge=1, le=100)


class RiskPoint(BaseModel):
    id: int | None = None
    task_id: int | None = None
    session_id: int | None = None
    index: int
    original_content: str
    risk_analysis: str
    risk_level: str = Field(..., pattern="^(高|中|低)$")
    suggested_content: str
    risk_dim: str = ""


class AcceptRiskPointRequest(BaseModel):
    session_id: int
    task_id: int
    index: int
    is_accepted: int = Field(..., ge=0, le=1)


class AcceptContractFileRequest(BaseModel):
    file_id: int
    is_accepted: int = Field(..., ge=0, le=1)
