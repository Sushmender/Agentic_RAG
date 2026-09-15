"""
backend/app/api/v1/endpoints/documents.py
Document upload and retrieval endpoints.
POST /documents/upload   — Day 1 (full implementation)
GET  /documents/         — Day 1 (full implementation)
GET  /documents/{id}     — Day 1 (full implementation)
GET  /documents/{id}/chunks/{chunk_id} — Day 3 (full implementation)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile, File, status
from fastapi.responses import JSONResponse

from app.core.security import get_current_user_id
from app.schemas.document import DocumentUploadResponse, DocumentMetadata, DocumentListResponse

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document for multimodal RAG ingestion",
    description="Accepts PDF, DOCX, PPTX, XLSX, or image files. Returns document_id + job_id immediately. Ingestion is async.",
)
async def upload_document(
    file: UploadFile = File(..., description="Document file to ingest"),
    user_id: str = Depends(get_current_user_id),
) -> DocumentUploadResponse:
    """Full implementation: Day 1."""
    raise NotImplementedError("POST /documents/upload — implemented Day 1")


@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List all documents for the authenticated user",
)
async def list_documents(
    user_id: str = Depends(get_current_user_id),
) -> DocumentListResponse:
    """Full implementation: Day 1."""
    raise NotImplementedError("GET /documents/ — implemented Day 1")


@router.get(
    "/{document_id}",
    response_model=DocumentMetadata,
    summary="Get document metadata and ingestion status",
)
async def get_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
) -> DocumentMetadata:
    """Full implementation: Day 1."""
    raise NotImplementedError("GET /documents/{document_id} — implemented Day 1")


@router.get(
    "/{document_id}/chunks/{chunk_id}",
    summary="Get a specific chunk from a processed document",
)
async def get_chunk(
    document_id: str,
    chunk_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Full implementation: Day 3."""
    raise NotImplementedError("GET /documents/{document_id}/chunks/{chunk_id} — implemented Day 3")
