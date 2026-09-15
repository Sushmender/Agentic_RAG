"""
backend/app/api/v1/endpoints/health.py
Health check endpoint.
Returns status of backend, ChromaDB, and Redis.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.db import chromadb_client, redis_client

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    summary="Health check",
    description="Returns health status of the API, ChromaDB, and Redis.",
    response_model=dict,
)
async def health_check() -> dict:
    chroma_ok = chromadb_client.is_healthy()
    redis_ok = await redis_client.is_healthy()

    status = "ok" if (chroma_ok and redis_ok) else "degraded"

    return {
        "status": status,
        "version": "0.1.0",
        "components": {
            "chromadb": "ok" if chroma_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
    }


@router.head("/health", include_in_schema=False)
async def health_head() -> None:
    """HEAD /health — for uptime checks."""
    return None
