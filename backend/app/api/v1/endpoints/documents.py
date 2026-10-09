"""
backend/app/api/v1/endpoints/documents.py
Document upload and retrieval endpoints.

POST /documents/upload   — multipart upload, magic-byte MIME validation,
                           SHA-256 idempotency, file storage, async ingestion
GET  /documents/         — list all documents for authenticated user
GET  /documents/{id}     — single document metadata
GET  /documents/{id}/chunks/{chunk_id} — fetch chunk from ChromaDB
"""
from __future__ import annotations

import hashlib
import io
import shutil
import uuid
import zipfile
from pathlib import Path
from datetime import datetime, timezone

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, status, Response

try:
    import magic as _magic  # type: ignore
    # Test-call to catch Windows DLL load failures (OSError) at startup,
    # not silently at request time. python-magic-bin can fail with OSError
    # if libmagic.dll is missing even when the import itself succeeds.
    _magic.from_buffer(b"\x25\x50\x44\x46", mime=True)  # "%PDF" magic bytes
    _MAGIC_AVAILABLE = True
except Exception:
    _magic = None  # type: ignore
    _MAGIC_AVAILABLE = False

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import get_current_user_id
from app.db.chromadb_client import get_chunk_by_id, delete_document
from app.db.sqlite_store import document_store, job_store
from app.services.cache_service import invalidate_document_cache
from app.schemas.chunk import ChunkResponse
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


def _inspect_ooxml_mimetype(file_bytes: bytes) -> str | None:
    """Inspect a ZIP container to identify Office OpenXML document types (DOCX, PPTX, XLSX)."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            names = zf.namelist()
            if any(name.startswith("word/") for name in names):
                return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if any(name.startswith("ppt/") for name in names):
                return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            if any(name.startswith("xl/") for name in names):
                return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except Exception:
        pass
    return None


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

    # ── 3. Validate MIME type using magic bytes (with client content_type fallback) ──
    if _MAGIC_AVAILABLE:
        detected_mime = _magic.from_buffer(file_bytes[:4096], mime=True)
        content_type = detected_mime.split(";")[0].strip().lower()
        log.debug("MIME detected via magic bytes", detected_mime=content_type)
    else:
        # Fallback: use browser-reported content type (less secure)
        content_type = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
        log.warning("python-magic unavailable — using client-reported MIME type", content_type=content_type)

    # Office OpenXML files (.docx, .pptx, .xlsx) are ZIP archives; libmagic often detects them as application/zip
    if content_type in ("application/zip", "application/x-zip-compressed", "application/octet-stream"):
        ooxml_type = _inspect_ooxml_mimetype(file_bytes)
        if ooxml_type:
            content_type = ooxml_type
            log.debug("OOXML container identified", detected_mime=content_type)

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
    safe_filename = Path(file.filename or "upload").name  # strip path traversal
    log = log.bind(document_id=document_id, filename=safe_filename)

    # ── 5. Idempotency check (exact content duplicate) ───────────────────────
    existing_doc = await document_store.get(document_id, user_id=user_id)
    if existing_doc is not None:
        existing_job = await job_store.get_by_document(document_id)
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

    # ── 5b. Overwrite / Replace previous document with same filename ─────────
    # When a modified version of an existing file is uploaded, remove the old
    # document's ChromaDB embeddings, cache entries, and database records.
    old_docs = await document_store.get_by_filename(safe_filename, user_id=user_id)
    for old_doc in old_docs:
        if old_doc.document_id != document_id:
            log.info(
                "Replacing existing document with same filename",
                old_document_id=old_doc.document_id,
                filename=safe_filename,
            )
            # Remove old chunks from ChromaDB
            try:
                delete_document(old_doc.document_id)
            except Exception as e:
                log.warning("Failed to delete old ChromaDB chunks during overwrite", error=str(e))

            # Invalidate Redis cache
            try:
                await invalidate_document_cache(old_doc.document_id)
            except Exception as e:
                log.warning("Failed to invalidate cache during overwrite", error=str(e))

            # Remove old record from SQLite
            await document_store.delete(old_doc.document_id, user_id=user_id)
            await job_store.delete_by_document(old_doc.document_id)

            # Clean up old upload disk folder
            try:
                old_upload_dir = settings.get_upload_dir() / old_doc.document_id
                if old_upload_dir.exists():
                    shutil.rmtree(old_upload_dir, ignore_errors=True)
                old_ade_dir = Path(settings.ADE_OUTPUT_DIR) / old_doc.document_id
                if old_ade_dir.exists():
                    shutil.rmtree(old_ade_dir, ignore_errors=True)
            except Exception:
                pass

    # ── 6. Persist file to disk ───────────────────────────────────────────────
    upload_dir: Path = settings.get_upload_dir() / document_id
    upload_dir.mkdir(parents=True, exist_ok=True)
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
    await document_store.save(doc)

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
    await job_store.save(job)

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
    docs = await document_store.list_for_user(user_id)
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
    doc = await document_store.get(document_id, user_id=user_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    return doc


# ── Get chunk (Day 3) ──────────────────────────────────────────────────────────

@router.get(
    "/{document_id}/chunks/{chunk_id}",
    response_model=ChunkResponse,
    summary="Get a specific chunk from a processed document",
    description=(
        "Fetch a single chunk's metadata and text from ChromaDB. "
        "Returns 404 if the chunk does not exist or does not belong to the specified document."
    ),
)
async def get_chunk(
    document_id: str,
    chunk_id: str,
    user_id: str = Depends(get_current_user_id),
) -> ChunkResponse:
    """Full ChromaDB implementation — Day 3."""
    # Verify the parent document exists and belongs to this user
    doc = await document_store.get(document_id, user_id=user_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    # Fetch chunk from ChromaDB
    chunk_data = get_chunk_by_id(chunk_id)
    if chunk_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chunk '{chunk_id}' not found in ChromaDB.",
        )

    # Security check: ensure chunk belongs to the requested document
    if chunk_data.get("document_id") != document_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chunk '{chunk_id}' does not belong to document '{document_id}'.",
        )

    return ChunkResponse(
        chunk_id=chunk_data["chunk_id"],
        document_id=chunk_data["document_id"],
        chunk_type=chunk_data["chunk_type"],
        text=chunk_data["text"],
        page=chunk_data["page"],
        bbox=chunk_data["bbox"],
        source=chunk_data["source"],
        parser_version=chunk_data["parser_version"],
    )


# ── Delete document ───────────────────────────────────────────────────────────

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a document and its indexed chunks",
    description="Deletes document metadata from SQLite, all chunks from ChromaDB, cached queries, and local files.",
)
async def delete_document_endpoint(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
) -> Response:
    doc = await document_store.get(document_id, user_id=user_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    # 1. Delete ChromaDB chunks
    try:
        delete_document(document_id)
    except Exception as e:
        logger.warning("Failed to delete ChromaDB chunks on delete", error=str(e))

    # 2. Invalidate Redis cache
    try:
        await invalidate_document_cache(document_id)
    except Exception as e:
        logger.warning("Failed to invalidate cache on delete", error=str(e))

    # 3. Delete from SQLite
    await document_store.delete(document_id, user_id=user_id)
    await job_store.delete_by_document(document_id)

    # 4. Remove disk folders
    try:
        upload_dir = settings.get_upload_dir() / document_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
        ade_dir = Path(settings.ADE_OUTPUT_DIR) / document_id
        if ade_dir.exists():
            shutil.rmtree(ade_dir, ignore_errors=True)
    except Exception:
        pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)
