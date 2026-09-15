"""
backend/app/api/v1/endpoints/query.py
Query endpoint — multimodal RAG pipeline.
POST /query — Full implementation: Day 5 (with Redis cache: Day 6).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_current_user_id
from app.schemas.query import QueryRequest, QueryResponse

router = APIRouter(prefix="/query", tags=["Query"])


@router.post(
    "",
    response_model=QueryResponse,
    summary="Ask a question about ingested documents",
    description=(
        "Runs the full multimodal RAG pipeline: "
        "route → embed → retrieve → rerank → assemble → generate. "
        "Checks Redis cache first. Returns grounded answer with source citations."
    ),
)
async def query(
    request: QueryRequest,
    user_id: str = Depends(get_current_user_id),
) -> QueryResponse:
    """Full implementation: Day 5 (cache: Day 6)."""
    raise NotImplementedError("POST /query — implemented Day 5")
