"""
backend/app/api/v1/endpoints/health.py
Health check endpoint.
Returns status of backend, ChromaDB, and Redis.
"""
from __future__ import annotations

import os
import uuid
from fastapi import APIRouter

from app.db import chromadb_client, redis_client

router = APIRouter(tags=["Health"])

BOOT_ID: str = os.getenv("APP_BOOT_ID") or str(uuid.uuid4())


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

    result = {
        "status": status,
        "version": "0.1.0",
        "boot_id": BOOT_ID,
        "components": {
            "chromadb": "ok" if chroma_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
    }

    # Optional guard check: embedding model mismatch between stored and current config
    mismatch = chromadb_client.check_embedding_model_mismatch()
    if mismatch is not None:
        result["embedding_model_mismatch"] = mismatch

    return result


@router.head("/health", include_in_schema=False)
async def health_head() -> None:
    """HEAD /health — for uptime checks."""
    return None
