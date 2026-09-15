"""
backend/app/api/v1/endpoints/jobs.py
Ingestion job status endpoint.
GET /jobs/{job_id} — Full implementation: Day 1.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_current_user_id
from app.schemas.job import JobResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get ingestion job status",
    description="Poll this endpoint to track async document ingestion progress.",
)
async def get_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
) -> JobResponse:
    """Full implementation: Day 1."""
    raise NotImplementedError("GET /jobs/{job_id} — implemented Day 1")
