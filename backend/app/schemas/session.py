from datetime import datetime

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: str
    session_type: str = Field(..., pattern="^(review|compare|chat)$")
    file_id: int | None = None


class ListSessionRequest(BaseModel):
    session_type: str = Field(..., pattern="^(review|compare|chat)$")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class UpdateSessionTitleRequest(BaseModel):
    session_id: int
    new_title: str


class DeleteSessionRequest(BaseModel):
    session_id: int


class SessionResponse(BaseModel):
    session_id: int
    title: str
    session_type: str
    file_id: int | None = None
    created_at: datetime | None = None


class ReviewSessionResponse(SessionResponse):
    party_a: str = ""
    party_b: str = ""
    is_accepted: int = 0


class CompareSessionResponse(SessionResponse):
    file_id_2: int | None = None
    party_a_2: str = ""
    party_b_2: str = ""


class HistoryRequest(BaseModel):
    session_id: int
