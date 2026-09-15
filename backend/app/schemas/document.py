"""
backend/app/schemas/document.py
Pydantic models for Document and DocumentMetadata.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    WEBP = "webp"
    TIFF = "tiff"
    UNKNOWN = "unknown"


class DocumentMetadata(BaseModel):
    """Full document metadata stored and returned by the API."""
    document_id: str = Field(..., description="SHA-256 hash of file content — stable identifier")
    filename: str = Field(..., description="Original uploaded filename")
    document_type: DocumentType = Field(..., description="File type enum")
    mime_type: str = Field(..., description="Detected MIME type")
    file_size_bytes: int = Field(..., description="File size in bytes")
    version: int = Field(default=1, description="Document version (increments on re-upload)")
    status: DocumentStatus = Field(default=DocumentStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str = Field(..., description="Owner user ID")
    source: str = Field(default="", description="Upload source identifier")
    parser_version: Optional[str] = Field(default=None, description="ADE parser version used")
    chunk_count: int = Field(default=0, description="Number of chunks after ADE processing")
    ade_credits_used: float = Field(default=0.0, description="ADE credits consumed for this document")
    error_message: Optional[str] = Field(default=None, description="Error detail if status=failed")


class DocumentUploadResponse(BaseModel):
    """Response returned immediately after a successful upload."""
    document_id: str
    job_id: str
    status: DocumentStatus
    message: str = "Document accepted for processing."


class DocumentListResponse(BaseModel):
    """Paginated list of documents for the authenticated user."""
    documents: list[DocumentMetadata]
    total: int
