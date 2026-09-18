"""
backend/app/api/v1/endpoints/documents.py
Document upload and retrieval endpoints — full Day 1 implementation.

POST /documents/upload   — multipart upload, MIME validation, SHA-256 idempotency,
                           file storage, async ingestion via BackgroundTasks
GET  /documents/         — list all documents for authenticated user
GET  /documents/{id}     — single document metadata
GET  /documents/{id}/chunks/{chunk_id} — Day 3 (stub still)
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from datetime import datetime, timezone

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import get_current_user_id
from app.db.in_memory_store import document_store, job_store
from app.schemas.document import (
    DocumentMetadata,
    DocumentStatus,
    DocumentType,
    DocumentUploadResponse,
    DocumentListResponse,
)
from app.schemas.job import Job, JobStatus
from app.services.ingestion_service import run_ingestion

router = APIRouter(prefix="/documents", tags=["Documents"])
settings = get_settings()
logger = get_logger(__name__)

# ── MIME type → DocumentType mapping ──────────────────────────────────────────

_MIME_TO_DOC_TYPE: dict[str, DocumentType] = {
    "application/pdf": DocumentType.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentType.DOCX,
    "application/msword": DocumentType.DOCX,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": DocumentType.PPTX,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": DocumentType.XLSX,
    "image/png": DocumentType.PNG,
    "image/jpeg": DocumentType.JPG,
    "image/jpg": DocumentType.JPG,
    "image/webp": DocumentType.WEBP,
    "image/tiff": DocumentType.TIFF,
}


def _detect_doc_type(mime: str, filename: str) -> DocumentType:
    """Best-effort document type from MIME, fall back to extension."""
    doc_type = _MIME_TO_DOC_TYPE.get(mime.lower())
    if doc_type:
        return doc_type
    ext = Path(filename).suffix.lower().lstrip(".")
    try:
        return DocumentType(ext)
    except ValueError:
        return DocumentType.UNKNOWN


# ── Upload endpoint ────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document for multimodal RAG ingestion",
    description=(
        "Accepts PDF, DOCX, PPTX, XLSX, or image files. "
        "Returns document_id + job_id immediately. "
        "Same file uploaded twice returns the same document_id (idempotent). "
        "Ingestion runs asynchronously in the background."
    ),
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Document file to ingest"),
    user_id: str = Depends(get_current_user_id),
) -> DocumentUploadResponse:
    """Full implementation: Day 1."""
    log = logger.bind(user_id=user_id, filename=file.filename)

    # ── 1. Read file bytes ────────────────────────────────────────────────────
    file_bytes = await file.read()
    file_size = len(file_bytes)

    # ── 2. Enforce size limit ─────────────────────────────────────────────────
    if file_size > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size {file_size / 1024 / 1024:.1f} MB exceeds "
                f"the {settings.MAX_UPLOAD_SIZE_MB} MB limit."
            ),
        )

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty.",
        )

    # ── 3. Validate MIME type ─────────────────────────────────────────────────
    # Use the content_type reported by the client (Day 8 adds magic-byte validation)
    content_type = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if content_type not in [m.lower() for m in settings.ALLOWED_MIME_TYPES]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File type '{content_type}' is not supported. "
                f"Allowed: {', '.join(settings.ALLOWED_MIME_TYPES)}"
            ),
        )

    # ── 4. Compute stable document_id = SHA-256(file_bytes) ──────────────────
    document_id = hashlib.sha256(file_bytes).hexdigest()
    log = log.bind(document_id=document_id)

    # ── 5. Idempotency check ──────────────────────────────────────────────────
    existing_doc = document_store.get(document_id, user_id=user_id)
    if existing_doc is not None:
        existing_job = job_store.get_by_document(document_id)
        job_id = existing_job.job_id if existing_job else "unknown"
        log.info(
            "Duplicate upload detected — returning existing record",
            status=existing_doc.status,
        )
        return DocumentUploadResponse(
            document_id=document_id,
            job_id=job_id,
            status=existing_doc.status,
            message="Document already exists. Returning existing record.",
        )

    # ── 6. Persist file to disk ───────────────────────────────────────────────
    upload_dir: Path = settings.get_upload_dir() / document_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = Path(file.filename or "upload").name  # strip path traversal
    file_path = upload_dir / safe_filename

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(file_bytes)

    log.info("File saved", file_path=str(file_path), size_bytes=file_size)

    # ── 7. Create document metadata record ────────────────────────────────────
    doc_type = _detect_doc_type(content_type, file.filename or "")
    now = datetime.now(timezone.utc)
    doc = DocumentMetadata(
        document_id=document_id,
        filename=safe_filename,
        document_type=doc_type,
        mime_type=content_type,
        file_size_bytes=file_size,
        version=1,
        status=DocumentStatus.PENDING,
        created_at=now,
        updated_at=now,
        user_id=user_id,
        source=safe_filename,
    )
    document_store.save(doc)

    # ── 8. Create job record ──────────────────────────────────────────────────
    job_id = str(uuid.uuid4())
    job = Job(
        job_id=job_id,
        document_id=document_id,
        user_id=user_id,
        status=JobStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    job_store.save(job)

    log.info("Job created", job_id=job_id, status="pending")

    # ── 9. Enqueue background ingestion ──────────────────────────────────────
    background_tasks.add_task(
        run_ingestion,
        document_id=document_id,
        job_id=job_id,
        file_path=str(file_path),
        user_id=user_id,
    )

    return DocumentUploadResponse(
        document_id=document_id,
        job_id=job_id,
        status=DocumentStatus.PENDING,
        message="Document accepted for processing.",
    )


# ── List documents ─────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List all documents for the authenticated user",
)
async def list_documents(
    user_id: str = Depends(get_current_user_id),
) -> DocumentListResponse:
    """Returns all documents owned by the authenticated user, newest first."""
    docs = document_store.list_for_user(user_id)
    return DocumentListResponse(documents=docs, total=len(docs))


# ── Get single document ────────────────────────────────────────────────────────

@router.get(
    "/{document_id}",
    response_model=DocumentMetadata,
    summary="Get document metadata and ingestion status",
)
async def get_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
) -> DocumentMetadata:
    """Returns document metadata including current ingestion status."""
    doc = document_store.get(document_id, user_id=user_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    return doc


# ── Get chunk (Day 3) ──────────────────────────────────────────────────────────

@router.get(
    "/{document_id}/chunks/{chunk_id}",
    summary="Get a specific chunk from a processed document",
)
async def get_chunk(
    document_id: str,
    chunk_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Full implementation: Day 3 (ChromaDB chunk fetch)."""
    raise NotImplementedError("GET /documents/{document_id}/chunks/{chunk_id} — implemented Day 3")
