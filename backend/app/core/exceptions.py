"""Unified exception handling: every error returns GenericResponse envelope."""
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.base import GenericResponse


def _body(code: int, msg: str, data: Any = None) -> dict:
    return GenericResponse(code=code, msg=msg, data=data).model_dump()


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.status_code, str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_body(422, "Validation error", {"errors": exc.errors()}),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=_body(500, f"Internal error: {exc}"),
        )
