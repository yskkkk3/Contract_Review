
from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    file_id: int
    title: str
    file_type: str
    file_url: str
    party_a: str = ""
    party_b: str = ""
    amount: float = 0.0
    parse_status: str = "parsed"


class SetContractTypeRequest(BaseModel):
    contract_type_id: int
    review_position: int = Field(0, ge=0, le=1, description="0 甲方 / 1 乙方")


class ContractFileResponse(BaseModel):
    id: int
    title: str
    file_type: str
    party_a: str = ""
    party_b: str = ""
    amount: float = 0.0
    contract_type_id: int | None = None
    review_position: int = 0
    is_accepted: int = 0
    created_at: str | None = None
