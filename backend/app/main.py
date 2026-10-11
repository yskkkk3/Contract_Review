"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    auth,
    chats,
    comparisons,
    contracts,
    dashboard,
    metrics,
    reviews,
    sessions,
    users,
)
from app.core.config import get_settings
from app.core.db import Base, engine
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis, init_redis
from app.middlewares.auth import AuthMiddleware
from app.middlewares.logging import RequestLogMiddleware
from app.middlewares.ratelimit import RateLimitMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    await init_redis()
    yield
    await close_redis()


app = FastAPI(
    title=f"{settings.app_name} API",
    version="0.3.0",
    description="高校合同智能审阅 Agent：LangGraph 编排 + 混合 RAG + 规则引擎 + MCP 接入。\n\n- Swagger: /docs\n- ReDoc: /redoc\n- OpenAPI JSON: /openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

if settings.auth_middleware_enabled:
    app.add_middleware(AuthMiddleware)
if settings.rate_limit_enabled:
    app.add_middleware(RateLimitMiddleware)
if settings.request_log_enabled:
    app.add_middleware(RequestLogMiddleware)

app.include_router(auth.router, prefix="/api/auth")
app.include_router(users.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(contracts.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(comparisons.router, prefix="/api")
app.include_router(chats.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")

if settings.mcp_enabled:
    from app.mcp.server import get_fastmcp_app

    app.mount("/api/mcp", get_fastmcp_app())


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "app": settings.app_name}
