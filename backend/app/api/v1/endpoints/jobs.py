"""
backend/app/api/v1/endpoints/jobs.py
Ingestion job status endpoint — full Day 1 implementation.
GET /jobs/{job_id}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.logging import get_logger
from app.core.security import get_current_user_id
from app.db.in_memory_store import job_store
from app.schemas.job import JobResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])
logger = get_logger(__name__)


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get ingestion job status",
    description=(
        "Poll this endpoint to track async document ingestion progress. "
        "Status transitions: pending → processing → completed | failed."
    ),
)
async def get_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
) -> JobResponse:
    """Returns current job status. Raises 404 if job not found, 403 if not owned by user."""
    job = job_store.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if job.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this job.",
        )

    return JobResponse(
        job_id=job.job_id,
        document_id=job.document_id,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error_message=job.error_message,
        progress_message=job.progress_message,
        chunks_created=job.chunks_created,
    )
