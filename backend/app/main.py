"""FastAPI application entrypoint."""
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    auth,
    avatars,
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
from app.core.db import Base, SessionLocal, engine
from app.core.exceptions import register_exception_handlers
from app.core.langfuse import shutdown_langfuse
from app.core.redis import close_redis, init_redis
from app.mcp.client import mcp_client_manager
from app.middlewares.auth import AuthMiddleware
from app.middlewares.logging import RequestLogMiddleware
from app.middlewares.ratelimit import RateLimitMiddleware
from app.services.contract_type_service import ensure_default_contract_types
from app.services.review_jobs import shutdown_review_jobs

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_default_contract_types(db)
        db.commit()
    await init_redis()
    try:
        async with AsyncExitStack() as stack:
            if settings.mcp_enabled:
                from app.mcp.server import get_mcp_server

                await stack.enter_async_context(get_mcp_server().session_manager.run())
                await mcp_client_manager.connect_all()
            yield
    finally:
        try:
            await shutdown_review_jobs()
            await mcp_client_manager.close_all()
            from app.rag import client as client_mod

            if client_mod._llm_client is not None:
                await client_mod._llm_client.aclose()
                client_mod._llm_client = None
        finally:
            try:
                await asyncio.to_thread(shutdown_langfuse)
            finally:
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
    expose_headers=["X-Access-Token"],
)

register_exception_handlers(app)

if settings.auth_middleware_enabled:
    app.add_middleware(AuthMiddleware)
if settings.rate_limit_enabled:
    app.add_middleware(RateLimitMiddleware)
if settings.request_log_enabled:
    app.add_middleware(RequestLogMiddleware)

app.include_router(auth.router, prefix="/api/auth")
app.include_router(avatars.router, prefix="/api")
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
