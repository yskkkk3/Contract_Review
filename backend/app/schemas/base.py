from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class GenericResponse(BaseModel, Generic[T]):
    code: int = 200
    msg: str = "success"
    data: T | None = None


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
