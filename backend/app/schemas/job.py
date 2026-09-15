"""
backend/app/schemas/job.py
Pydantic models for async ingestion jobs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    INGESTION = "ingestion"


class Job(BaseModel):
    """Represents an async ingestion job."""
    job_id: str = Field(..., description="Unique job identifier (UUID)")
    document_id: str = Field(..., description="Document being processed")
    user_id: str = Field(..., description="Owner user ID")
    job_type: JobType = Field(default=JobType.INGESTION)
    status: JobStatus = Field(default=JobStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    error_message: Optional[str] = Field(default=None, description="Error detail if status=failed")
    progress_message: Optional[str] = Field(default=None, description="Human-readable progress note")

    # Telemetry
    ade_credits_used: float = Field(default=0.0)
    chunks_created: int = Field(default=0)
    chunks_embedded: int = Field(default=0)


class JobResponse(BaseModel):
    """Slimmed job response for API."""
    job_id: str
    document_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
    progress_message: Optional[str] = None
    chunks_created: int = 0
