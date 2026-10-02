"""
backend/app/db/sqlite_store.py
SQLite-backed persistent stores for DocumentMetadata and Job records.

Replaces the in-memory stores (db/in_memory_store.py) from Day 1–6.
State survives server restarts — job status and document metadata are durable.

Design:
  - Same interface as DocumentStore / JobStore in in_memory_store.py
    so all callers can swap imports without logic changes.
  - Uses aiosqlite for async SQLite access (no sync blocking).
  - Tables created via init_sqlite() called in app lifespan.
  - SQLite DB file: data/rag.db (gitignored via data/ rule)

Tables:
  documents — one row per document_id
  jobs      — one row per job_id, secondary index on document_id
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import aiosqlite

from app.core.logging import get_logger
from app.schemas.document import DocumentMetadata, DocumentStatus
from app.schemas.job import Job, JobStatus

logger = get_logger(__name__)

_DB_PATH = Path("./data/rag.db")

# ── DDL ────────────────────────────────────────────────────────────────────────

_CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    document_id     TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    filename        TEXT,
    document_type   TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    chunk_count     INTEGER,
    parser_version  TEXT,
    ade_credits_used REAL,
    embedding_model TEXT,
    error_message   TEXT,
    file_path       TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

_CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    user_id         TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    progress_message TEXT,
    error_message   TEXT,
    chunks_created  INTEGER,
    chunks_embedded INTEGER,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT
);
"""

_CREATE_JOB_DOC_INDEX = """
CREATE INDEX IF NOT EXISTS idx_jobs_document_id ON jobs(document_id);
"""

_CREATE_DOC_USER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
"""

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    username        TEXT UNIQUE NOT NULL,
    email           TEXT NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);
"""


async def init_sqlite() -> None:
    """Create tables and indexes. Called once during app lifespan startup."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(_CREATE_DOCUMENTS)
        await db.execute(_CREATE_JOBS)
        await db.execute(_CREATE_JOB_DOC_INDEX)
        await db.execute(_CREATE_DOC_USER_INDEX)
        await db.execute(_CREATE_USERS)
        await db.commit()
    logger.info("SQLite store initialised", db_path=str(_DB_PATH))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_from_row(row: aiosqlite.Row) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=row["document_id"],
        user_id=row["user_id"],
        filename=row["filename"] or "",
        document_type=row["document_type"] or "",
        status=DocumentStatus(row["status"]),
        chunk_count=row["chunk_count"],
        parser_version=row["parser_version"],
        ade_credits_used=row["ade_credits_used"],
        embedding_model=row["embedding_model"],
        error_message=row["error_message"],
        file_path=row["file_path"],
        mime_type="",           # not persisted in SQLite — display-only field
        file_size_bytes=0,      # not persisted in SQLite — display-only field
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _job_from_row(row: aiosqlite.Row) -> Job:
    return Job(
        job_id=row["job_id"],
        document_id=row["document_id"],
        user_id=row["user_id"],
        status=JobStatus(row["status"]),
        progress_message=row["progress_message"],
        error_message=row["error_message"],
        chunks_created=row["chunks_created"],
        chunks_embedded=row["chunks_embedded"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


# ── DocumentSQLiteStore ────────────────────────────────────────────────────────

class DocumentSQLiteStore:
    """
    Async SQLite-backed store for DocumentMetadata.
    Same interface as DocumentStore in in_memory_store.py.
    """

    async def save(self, doc: DocumentMetadata) -> None:
        """Insert or replace a document record (upsert by document_id)."""
        async with aiosqlite.connect(_DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO documents
                    (document_id, user_id, filename, document_type, status,
                     chunk_count, parser_version, ade_credits_used, embedding_model,
                     error_message, file_path, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(document_id) DO UPDATE SET
                    status          = excluded.status,
                    chunk_count     = excluded.chunk_count,
                    parser_version  = excluded.parser_version,
                    ade_credits_used= excluded.ade_credits_used,
                    embedding_model = excluded.embedding_model,
                    error_message   = excluded.error_message,
                    file_path       = excluded.file_path,
                    updated_at      = excluded.updated_at
                """,
                (
                    doc.document_id, doc.user_id, doc.filename, doc.document_type,
                    doc.status.value,
                    doc.chunk_count, doc.parser_version, doc.ade_credits_used,
                    doc.embedding_model, doc.error_message,
                    getattr(doc, "file_path", None),
                    doc.created_at.isoformat(), doc.updated_at.isoformat(),
                ),
            )
            await db.commit()

    async def get(self, document_id: str, user_id: str | None = None) -> Optional[DocumentMetadata]:
        """Fetch a document by ID. If user_id provided, enforces ownership."""
        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            if user_id:
                cur = await db.execute(
                    "SELECT * FROM documents WHERE document_id=? AND user_id=?",
                    (document_id, user_id),
                )
            else:
                cur = await db.execute(
                    "SELECT * FROM documents WHERE document_id=?",
                    (document_id,),
                )
            row = await cur.fetchone()
        return _doc_from_row(row) if row else None

    async def list_for_user(self, user_id: str) -> List[DocumentMetadata]:
        """Return all documents owned by user_id, most recent first."""
        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM documents WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            )
            rows = await cur.fetchall()
        return [_doc_from_row(r) for r in rows]

    async def update_status(
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
        """Mutate status + optional fields on an existing document record."""
        now = _now_iso()
        async with aiosqlite.connect(_DB_PATH) as db:
            # Fetch existing to preserve unchanged fields
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM documents WHERE document_id=?", (document_id,)
            )
            row = await cur.fetchone()
            if row is None:
                return

            await db.execute(
                """
                UPDATE documents SET
                    status           = ?,
                    chunk_count      = COALESCE(?, chunk_count),
                    parser_version   = COALESCE(?, parser_version),
                    ade_credits_used = COALESCE(?, ade_credits_used),
                    embedding_model  = COALESCE(?, embedding_model),
                    error_message    = COALESCE(?, error_message),
                    updated_at       = ?
                WHERE document_id = ?
                """,
                (
                    status.value,
                    chunk_count, parser_version, ade_credits_used,
                    embedding_model, error_message,
                    now, document_id,
                ),
            )
            await db.commit()

    async def exists(self, document_id: str) -> bool:
        async with aiosqlite.connect(_DB_PATH) as db:
            cur = await db.execute(
                "SELECT 1 FROM documents WHERE document_id=?", (document_id,)
            )
            return await cur.fetchone() is not None

    async def count(self) -> int:
        async with aiosqlite.connect(_DB_PATH) as db:
            cur = await db.execute("SELECT COUNT(*) FROM documents")
            row = await cur.fetchone()
            return row[0] if row else 0


# ── JobSQLiteStore ─────────────────────────────────────────────────────────────

class JobSQLiteStore:
    """
    Async SQLite-backed store for Job records.
    Same interface as JobStore in in_memory_store.py.
    """

    async def save(self, job: Job) -> None:
        """Insert or replace a job record."""
        async with aiosqlite.connect(_DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO jobs
                    (job_id, document_id, user_id, status, progress_message,
                     error_message, chunks_created, chunks_embedded,
                     created_at, updated_at, started_at, completed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status           = excluded.status,
                    progress_message = excluded.progress_message,
                    error_message    = excluded.error_message,
                    chunks_created   = excluded.chunks_created,
                    chunks_embedded  = excluded.chunks_embedded,
                    updated_at       = excluded.updated_at,
                    started_at       = excluded.started_at,
                    completed_at     = excluded.completed_at
                """,
                (
                    job.job_id, job.document_id, getattr(job, "user_id", None),
                    job.status.value,
                    job.progress_message, job.error_message,
                    job.chunks_created, job.chunks_embedded,
                    job.created_at.isoformat(), job.updated_at.isoformat(),
                    job.started_at.isoformat() if job.started_at else None,
                    job.completed_at.isoformat() if job.completed_at else None,
                ),
            )
            await db.commit()

    async def get(self, job_id: str) -> Optional[Job]:
        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,))
            row = await cur.fetchone()
        return _job_from_row(row) if row else None

    async def get_by_document(self, document_id: str) -> Optional[Job]:
        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM jobs WHERE document_id=? ORDER BY created_at DESC LIMIT 1",
                (document_id,),
            )
            row = await cur.fetchone()
        return _job_from_row(row) if row else None

    async def update_status(
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
        now = _now_iso()
        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,))
            row = await cur.fetchone()
            if row is None:
                return

            started_at = row["started_at"]
            if status == JobStatus.PROCESSING and started_at is None:
                started_at = now

            completed_at = row["completed_at"]
            if status in (JobStatus.COMPLETED, JobStatus.FAILED):
                completed_at = now

            await db.execute(
                """
                UPDATE jobs SET
                    status           = ?,
                    progress_message = COALESCE(?, progress_message),
                    error_message    = COALESCE(?, error_message),
                    chunks_created   = COALESCE(?, chunks_created),
                    chunks_embedded  = COALESCE(?, chunks_embedded),
                    updated_at       = ?,
                    started_at       = ?,
                    completed_at     = ?
                WHERE job_id = ?
                """,
                (
                    status.value,
                    progress_message, error_message,
                    chunks_created, chunks_embedded,
                    now, started_at, completed_at,
                    job_id,
                ),
            )
            await db.commit()

    async def exists(self, job_id: str) -> bool:
        async with aiosqlite.connect(_DB_PATH) as db:
            cur = await db.execute("SELECT 1 FROM jobs WHERE job_id=?", (job_id,))
            return await cur.fetchone() is not None

    async def count(self) -> int:
        async with aiosqlite.connect(_DB_PATH) as db:
            cur = await db.execute("SELECT COUNT(*) FROM jobs")
            row = await cur.fetchone()
            return row[0] if row else 0


class UserSQLiteStore:
    """SQLite-backed store for User records."""

    async def save(self, user: dict) -> None:
        async with aiosqlite.connect(_DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO users (user_id, username, email, hashed_password, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    email = excluded.email,
                    hashed_password = excluded.hashed_password,
                    is_active = excluded.is_active
                """,
                (
                    user["user_id"],
                    user["username"],
                    user["email"],
                    user["hashed_password"],
                    int(user.get("is_active", True)),
                    user["created_at"].isoformat() if hasattr(user["created_at"], "isoformat") else user["created_at"]
                )
            )
            await db.commit()

    async def get_by_username(self, username: str) -> Optional[dict]:
        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = await cur.fetchone()
            if not row:
                return None
            
            return {
                "user_id": row["user_id"],
                "username": row["username"],
                "email": row["email"],
                "hashed_password": row["hashed_password"],
                "is_active": bool(row["is_active"]),
                "created_at": datetime.fromisoformat(row["created_at"])
            }


# ── Module-level singletons ────────────────────────────────────────────────────

document_store = DocumentSQLiteStore()
job_store = JobSQLiteStore()
user_store = UserSQLiteStore()
