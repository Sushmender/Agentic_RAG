"""
backend/app/main.py
FastAPI application factory.
- Lifespan: init ChromaDB, init Redis
- CORS, global exception handler
- Router inclusion
- Request ID middleware
"""
from __future__ import annotations

import time
import traceback
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger, set_request_id
from app.db import chromadb_client, redis_client

settings = get_settings()
configure_logging(log_level=settings.LOG_LEVEL, json_logs=not settings.DEBUG)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Startup: initialize ChromaDB, Redis.
    Shutdown: close connections gracefully.
    """
    logger.info("Starting Multimodal RAG API", version=settings.APP_VERSION)

    # ── Startup ──────────────────────────────────────────────────────────────
    # Ensure data directories exist
    settings.get_upload_dir()
    settings.get_ade_output_dir()
    settings.get_chroma_db_path()

    # Initialize ChromaDB
    chromadb_client.init_chromadb()

    # Initialize Redis (non-fatal in development — warns if unavailable)
    try:
        await redis_client.init_redis()
    except Exception as exc:
        logger.warning(
            "Redis initialization failed — cache features disabled. "
            "Set REDIS_URL in .env to enable caching.",
            error=str(exc),
        )

    logger.info("All services initialized. Ready to serve.")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Shutting down Multimodal RAG API")
    await redis_client.close_redis()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Production-oriented Multimodal RAG API.\n\n"
            "Pipeline: INGEST → UNDERSTAND → CHUNK → EMBED → INDEX → "
            "ROUTE → RETRIEVE → RERANK → GENERATE → GROUND → DISPLAY → MEASURE"
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request ID middleware ──────────────────────────────────────────────
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        set_request_id(request_id)
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "HTTP request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=round(elapsed_ms, 2),
        )
        return response

    # ── Global exception handler ──────────────────────────────────────────
    @app.exception_handler(NotImplementedError)
    async def not_implemented_handler(request: Request, exc: NotImplementedError):
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content={
                "error_code": "NOT_IMPLEMENTED",
                "detail": str(exc),
                "request_id": request.headers.get("X-Request-ID", ""),
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception",
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": "INTERNAL_ERROR",
                "detail": "An unexpected error occurred. Please try again.",
                "request_id": request.headers.get("X-Request-ID", ""),
            },
        )

    # ── Routes ───────────────────────────────────────────────────────────────
    app.include_router(api_router)

    return app


app = create_app()
