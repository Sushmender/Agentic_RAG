"""
backend/app/services/ingestion_service.py
Async ingestion coordinator — runs as a FastAPI BackgroundTask.

Pipeline (Day 3):
  1. pending → processing
  2. Idempotency check: if chunks.json already exists → skip ADE + re-use
  3. Call real ADE provider → get raw result
  4. Persist raw JSON  → data/ade_outputs/{document_id}/raw.json
  5. Persist markdown  → data/ade_outputs/{document_id}/document.md
  6. Normalize chunks  → chunking_service.normalize_chunks()
  7. Persist chunks    → data/ade_outputs/{document_id}/chunks.json
  8. Update document metadata (parser_version, chunk_count, ade_credits_used)
  9. Embed new chunks  → embedding_service.index_chunks(document_id)
 10. → completed | failed

State machine: pending → processing → completed | failed
All transitions are logged with structlog: document_id, job_id, status, timestamp.
"""
from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.in_memory_store import document_store, job_store
from app.providers.ade import ade_provider
from app.schemas.document import DocumentStatus
from app.schemas.job import JobStatus
from app.services.chunking_service import normalize_chunks, parse_ade_metadata
from app.services import embedding_service

logger = get_logger(__name__)
settings = get_settings()


async def run_ingestion(
    *,
    document_id: str,
    job_id: str,
    file_path: str,
    user_id: str,
) -> None:
    """
    Async ingestion coordinator. Called via FastAPI BackgroundTasks.

    Steps (Day 3):
      1. Mark job → processing
      2. Idempotency: skip ADE if chunks.json already exists
      3. Call real ADE provider
      4. Persist raw.json, document.md
      5. Normalize chunks via chunking_service
      6. Persist chunks.json
      7. Embed new chunks via embedding_service.index_chunks()
      8. Update Document + Job → completed
      On any exception: mark job + document → failed, log error
    """
    log = logger.bind(document_id=document_id, job_id=job_id, user_id=user_id)
    ade_output_dir = Path(settings.ADE_OUTPUT_DIR) / document_id
    ade_output_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = ade_output_dir / "chunks.json"
    raw_path = ade_output_dir / "raw.json"
    md_path = ade_output_dir / "document.md"

    # ── Step 1: Transition to processing ─────────────────────────────────────
    job_store.update_status(
        job_id,
        JobStatus.PROCESSING,
        progress_message="Ingestion started",
    )
    document_store.update_status(document_id, DocumentStatus.PROCESSING)
    log.info("Ingestion started", status="processing")

    try:
        # ── Step 2: Idempotency check ──────────────────────────────────────────
        ade_result: dict[str, Any]
        chunk_dicts: list[dict[str, Any]]

        if chunks_path.exists() and raw_path.exists():
            log.info(
                "ADE cache hit — skipping API call",
                chunks_path=str(chunks_path),
                raw_path=str(raw_path),
            )
            ade_result = json.loads(raw_path.read_text(encoding="utf-8"))
            chunk_dicts = json.loads(chunks_path.read_text(encoding="utf-8"))
            # Parse metadata from cached raw result
            ade_meta = parse_ade_metadata(ade_result)

        else:
            # ── Step 3: Real ADE call ──────────────────────────────────────────
            log.info("Calling ADE provider (real)", file_path=file_path)
            job_store.update_status(
                job_id,
                JobStatus.PROCESSING,
                progress_message="Calling ADE parse API",
            )
            ade_result = await ade_provider.parse_document(
                file_path=file_path,
                document_id=document_id,
            )

            ade_meta = parse_ade_metadata(ade_result)
            log.info(
                "ADE parse complete",
                raw_chunk_count=len(ade_result.get("chunks", [])),
                credit_usage=ade_meta["credit_usage"],
                parser_version=ade_meta["parser_version"],
                page_count=ade_meta["page_count"],
                duration_ms=ade_meta["duration_ms"],
            )

            # ── Step 4: Persist raw ADE output ─────────────────────────────────
            raw_path.write_text(
                json.dumps(ade_result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            log.info("Persisted raw ADE output", path=str(raw_path))

            # Persist full document markdown
            doc_markdown = ade_result.get("markdown", "")
            md_path.write_text(doc_markdown, encoding="utf-8")
            log.info("Persisted document markdown", path=str(md_path))

            # ── Step 5: Normalize chunks ───────────────────────────────────────
            job_store.update_status(
                job_id,
                JobStatus.PROCESSING,
                progress_message="Normalizing chunks",
            )
            # Get source filename from document record
            doc = document_store.get(document_id)
            source = doc.filename if doc else Path(file_path).name

            chunks = normalize_chunks(
                ade_result,
                document_id=document_id,
                source=source,
            )

            # ── Step 6: Persist chunks.json ─────────────────────────────────────
            chunk_dicts = [c.model_dump() for c in chunks]
            chunks_path.write_text(
                json.dumps(chunk_dicts, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            log.info(
                "Persisted normalized chunks",
                path=str(chunks_path),
                chunk_count=len(chunk_dicts),
            )

        # ── Step 7: Collect chunk metadata for completion ───────────────────────
        chunk_count = len(chunk_dicts)
        parser_version = ade_meta.get("parser_version", "unknown")
        credits_used = float(ade_meta.get("credit_usage", 0.0))

        log.info(
            "Chunking complete",
            chunk_count=chunk_count,
            credits_used=credits_used,
            parser_version=parser_version,
        )

        # ── Step 9: Embed new chunks into ChromaDB ───────────────────────────
        job_store.update_status(
            job_id,
            JobStatus.PROCESSING,
            progress_message="Embedding chunks into ChromaDB",
        )
        embedding_result = await embedding_service.index_chunks(document_id)
        log.info(
            "Embedding step complete",
            new_chunks_indexed=embedding_result.new_chunks_indexed,
            skipped_chunks=embedding_result.skipped_chunks,
            embedding_model=embedding_result.embedding_model,
            latency_ms=embedding_result.latency_ms,
        )

        # ── Step 10: Mark completed ──────────────────────────────────────────
        job_store.update_status(
            job_id,
            JobStatus.COMPLETED,
            progress_message=(
                f"Ingestion complete — {chunk_count} chunks created, "
                f"{embedding_result.new_chunks_indexed} embedded"
            ),
            chunks_created=chunk_count,
            chunks_embedded=embedding_result.new_chunks_indexed,
        )
        document_store.update_status(
            document_id,
            DocumentStatus.COMPLETED,
            chunk_count=chunk_count,
            parser_version=parser_version,
            ade_credits_used=credits_used,
            embedding_model=embedding_result.embedding_model,
        )
        log.info(
            "Ingestion completed",
            status="completed",
            chunk_count=chunk_count,
            credits_used=credits_used,
            parser_version=parser_version,
            embedding_model=embedding_result.embedding_model,
        )


    except Exception as exc:
        # ── Error path: mark both job and document as failed ──────────────────
        error_msg = f"{type(exc).__name__}: {exc}"
        log.error(
            "Ingestion failed",
            status="failed",
            error=error_msg,
            traceback=traceback.format_exc(),
        )
        job_store.update_status(
            job_id,
            JobStatus.FAILED,
            error_message=error_msg,
            progress_message="Ingestion failed — see error_message",
        )
        document_store.update_status(
            document_id,
            DocumentStatus.FAILED,
            error_message=error_msg,
        )
