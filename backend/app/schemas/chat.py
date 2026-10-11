
from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: int | None = None
    content: str | None = None
    parent_id: int | None = None
