"""
backend/app/services/ingestion_service.py
Async ingestion coordinator — runs as a FastAPI BackgroundTask.

Day 1: ADE is called via stub (returns empty chunks).
Day 2: ADE stub is replaced with real LandingAI ADE integration.

State machine: pending → processing → completed | failed
All transitions are logged with structlog including document_id, job_id, status.
"""
from __future__ import annotations

import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.db.in_memory_store import document_store, job_store
from app.providers.ade import ade_provider
from app.schemas.document import DocumentStatus
from app.schemas.job import JobStatus

logger = get_logger(__name__)


async def run_ingestion(
    *,
    document_id: str,
    job_id: str,
    file_path: str,
    user_id: str,
) -> None:
    """
    Async ingestion coordinator. Called via FastAPI BackgroundTasks.

    Steps (Day 1):
      1. Mark job → processing
      2. Call ADE provider (stub in Day 1, real in Day 2)
      3. Mark job + document → completed
      On any exception: mark job + document → failed, log error

    Steps added in later days:
      Day 2: real ADE, chunking service, persist chunks.json
      Day 3: embedding service, ChromaDB indexing
    """
    log = logger.bind(document_id=document_id, job_id=job_id, user_id=user_id)

    # ── Step 1: Transition to processing ─────────────────────────────────────
    job_store.update_status(
        job_id,
        JobStatus.PROCESSING,
        progress_message="Ingestion started",
    )
    document_store.update_status(document_id, DocumentStatus.PROCESSING)
    log.info("Ingestion started", status="processing")

    try:
        # ── Step 2: ADE document parsing (stub in Day 1) ──────────────────────
        log.info("Calling ADE provider", file_path=file_path)
        ade_result: dict[str, Any] = await ade_provider.parse_document(
            file_path=file_path,
            document_id=document_id,
        )

        chunks = ade_result.get("chunks", [])
        parser_version = ade_result.get("parser_version", "stub-0.0")
        credits_used = ade_result.get("credits_used", 0.0)
        chunk_count = len(chunks)

        log.info(
            "ADE parse complete",
            chunk_count=chunk_count,
            credits_used=credits_used,
            parser_version=parser_version,
        )

        # ── Step 3: (Day 2+) chunking_service.normalize(ade_result) ──────────
        # ── Step 4: (Day 3+) embedding_service.index_chunks(document_id) ─────

        # ── Step 5: Mark completed ─────────────────────────────────────────────
        job_store.update_status(
            job_id,
            JobStatus.COMPLETED,
            progress_message=f"Ingestion complete — {chunk_count} chunks",
            chunks_created=chunk_count,
        )
        document_store.update_status(
            document_id,
            DocumentStatus.COMPLETED,
            chunk_count=chunk_count,
            parser_version=parser_version,
            ade_credits_used=credits_used,
        )
        log.info(
            "Ingestion completed",
            status="completed",
            chunk_count=chunk_count,
            elapsed_note="ADE stub — instant in Day 1",
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
