"""
backend/app/db/in_memory_store.py
Thread-safe (asyncio-safe) in-memory stores for documents and jobs.
Used in Day 1–6. Replaced by SQLite-backed store in Day 7.

Both stores are module-level singletons. No locking needed since Python's
asyncio event loop is single-threaded — concurrent coroutines are cooperative.
"""
from __future__ import annotations

from typing import Optional

from app.schemas.document import DocumentMetadata, DocumentStatus
from app.schemas.job import Job, JobStatus


# ── Document Store ─────────────────────────────────────────────────────────────

class DocumentStore:
    """
    In-memory store for DocumentMetadata records.
    Keyed by document_id. Supports per-user listing.
    """

    def __init__(self) -> None:
        self._store: dict[str, DocumentMetadata] = {}

    def save(self, doc: DocumentMetadata) -> None:
        """Insert or overwrite a document record."""
        self._store[doc.document_id] = doc

    def get(self, document_id: str, user_id: str | None = None) -> Optional[DocumentMetadata]:
        """
        Fetch a document by ID.
        If user_id is provided, returns None if the document belongs to a different user.
        """
        doc = self._store.get(document_id)
        if doc is None:
            return None
        if user_id is not None and doc.user_id != user_id:
            return None
        return doc

    def list_for_user(self, user_id: str) -> list[DocumentMetadata]:
        """Return all documents owned by user_id, most recent first."""
        docs = [d for d in self._store.values() if d.user_id == user_id]
        return sorted(docs, key=lambda d: d.created_at, reverse=True)

    def update_status(
        self,
        document_id: str,
        status: DocumentStatus,
        *,
        chunk_count: int | None = None,
        parser_version: str | None = None,
        ade_credits_used: float | None = None,
        embedding_model: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Mutate status fields on an existing document record."""
        from datetime import datetime, timezone
        doc = self._store.get(document_id)
        if doc is None:
            return
        doc.status = status
        doc.updated_at = datetime.now(timezone.utc)
        if chunk_count is not None:
            doc.chunk_count = chunk_count
        if parser_version is not None:
            doc.parser_version = parser_version
        if ade_credits_used is not None:
            doc.ade_credits_used = ade_credits_used
        if embedding_model is not None:
            doc.embedding_model = embedding_model
        if error_message is not None:
            doc.error_message = error_message

    def exists(self, document_id: str) -> bool:
        return document_id in self._store

    def count(self) -> int:
        return len(self._store)


# ── Job Store ──────────────────────────────────────────────────────────────────

class JobStore:
    """
    In-memory store for async ingestion Job records.
    Keyed by job_id. Secondary index by document_id.
    """

    def __init__(self) -> None:
        self._store: dict[str, Job] = {}                    # job_id → Job
        self._doc_index: dict[str, str] = {}                # document_id → job_id

    def save(self, job: Job) -> None:
        """Insert or overwrite a job record."""
        self._store[job.job_id] = job
        self._doc_index[job.document_id] = job.job_id

    def get(self, job_id: str) -> Optional[Job]:
        return self._store.get(job_id)

    def get_by_document(self, document_id: str) -> Optional[Job]:
        job_id = self._doc_index.get(document_id)
        if job_id is None:
            return None
        return self._store.get(job_id)

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        progress_message: str | None = None,
        error_message: str | None = None,
        chunks_created: int | None = None,
        chunks_embedded: int | None = None,
    ) -> None:
        """Mutate status and timestamps on an existing job record."""
        from datetime import datetime, timezone
        job = self._store.get(job_id)
        if job is None:
            return
        now = datetime.now(timezone.utc)
        job.status = status
        job.updated_at = now
        if status == JobStatus.PROCESSING and job.started_at is None:
            job.started_at = now
        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            job.completed_at = now
        if progress_message is not None:
            job.progress_message = progress_message
        if error_message is not None:
            job.error_message = error_message
        if chunks_created is not None:
            job.chunks_created = chunks_created
        if chunks_embedded is not None:
            job.chunks_embedded = chunks_embedded

    def exists(self, job_id: str) -> bool:
        return job_id in self._store

    def count(self) -> int:
        return len(self._store)


# ── Module-level singletons ────────────────────────────────────────────────────

document_store = DocumentStore()
job_store = JobStore()
