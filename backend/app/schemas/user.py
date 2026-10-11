from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class UserUpdate(BaseModel):
    username: str | None = None
    password: str | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    is_active: bool = True
    role: str = "user"
    created_at: datetime | None = None
