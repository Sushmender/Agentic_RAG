"""
backend/app/services/embedding_service.py
Orchestrates chunk embedding and ChromaDB indexing for Day 3.

Pipeline (called from ingestion_service after chunking):
  1. Load normalized chunks from data/ade_outputs/{document_id}/chunks.json
  2. Call get_existing_ids() → identify already-indexed chunk IDs
  3. Filter to only NEW chunks (idempotency — re-ingestion skips existing)
  4. Batch new chunks into EMBEDDING_BATCH_SIZE groups
  5. For each batch: embed_passages(texts) → upsert_chunks(chunks, embeddings)
  6. Log and return EmbeddingResult with counts + telemetry

Idempotency guarantee:
  - Same document re-ingested → chunks.json already exists (ADE cache hit)
  - get_existing_ids() returns the existing chunk IDs
  - New chunks = [] → early return, 0 API calls made
  - Logged as: "new_chunks_indexed: 0, skipped: N"
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.chromadb_client import get_existing_ids, upsert_chunks
from app.providers.openrouter_embedding import embedding_provider
from app.schemas.chunk import Chunk

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class EmbeddingResult:
    """Result returned by index_chunks() with idempotency + telemetry fields."""
    document_id: str
    total_chunks: int
    new_chunks_indexed: int
    skipped_chunks: int
    embedding_model: str
    # Set to 0 when all chunks were skipped (no API calls made)
    total_tokens: int = 0
    latency_ms: float = 0.0


async def index_chunks(document_id: str) -> EmbeddingResult:
    """
    Embed and index all new chunks for a document into ChromaDB.

    Loads chunks from data/ade_outputs/{document_id}/chunks.json,
    skips already-indexed chunk IDs, embeds remaining chunks in batches,
    and upserts to ChromaDB.

    Args:
        document_id: The SHA-256 document ID.

    Returns:
        EmbeddingResult with counts of new/skipped chunks and telemetry.

    Raises:
        FileNotFoundError: If chunks.json does not exist for this document_id.
        Exception:         Any embedding provider or ChromaDB error (propagated).
    """
    log = logger.bind(document_id=document_id)
    t0 = time.monotonic()

    # ── Step 1: Load chunks from disk ─────────────────────────────────────────
    chunks_path = Path(settings.ADE_OUTPUT_DIR) / document_id / "chunks.json"
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"chunks.json not found for document_id={document_id}. "
            "Run ingestion first."
        )

    raw_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    all_chunks: List[Chunk] = [Chunk(**c) for c in raw_chunks]
    total = len(all_chunks)

    log.info("Loaded chunks for embedding", total_chunks=total, chunks_path=str(chunks_path))

    if total == 0:
        log.warning("No chunks found — skipping embedding")
        return EmbeddingResult(
            document_id=document_id,
            total_chunks=0,
            new_chunks_indexed=0,
            skipped_chunks=0,
            embedding_model=embedding_provider.model,
        )

    # ── Step 2: Check which chunk_ids already exist in ChromaDB ───────────────
    all_ids = [c.chunk_id for c in all_chunks]
    existing_ids = get_existing_ids(all_ids)

    new_chunks = [c for c in all_chunks if c.chunk_id not in existing_ids]
    skipped = len(all_chunks) - len(new_chunks)

    log.info(
        "Embedding idempotency check",
        total=total,
        new=len(new_chunks),
        skipped=skipped,
    )

    # ── Step 3: Short-circuit if nothing new to index ─────────────────────────
    if not new_chunks:
        log.info(
            "All chunks already indexed — skipping embedding API calls",
            skipped=skipped,
        )
        return EmbeddingResult(
            document_id=document_id,
            total_chunks=total,
            new_chunks_indexed=0,
            skipped_chunks=skipped,
            embedding_model=embedding_provider.model,
            total_tokens=0,
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
        )

    # ── Step 4: Batch embed new chunks ────────────────────────────────────────
    batch_size = settings.EMBEDDING_BATCH_SIZE
    texts = [c.text for c in new_chunks]

    log.info(
        "Embedding new chunks",
        new_chunks=len(new_chunks),
        batch_size=batch_size,
        model=embedding_provider.model,
    )

    # embed_passages() handles batching internally; we pass all texts at once
    embeddings = await embedding_provider.embed_passages(texts=texts, batch_size=batch_size)

    if len(embeddings) != len(new_chunks):
        raise ValueError(
            f"Embedding count mismatch: expected {len(new_chunks)}, "
            f"got {len(embeddings)}"
        )

    # ── Step 5: Upsert into ChromaDB in batches ───────────────────────────────
    indexed = 0
    for batch_start in range(0, len(new_chunks), batch_size):
        batch_chunks = new_chunks[batch_start : batch_start + batch_size]
        batch_embeddings = embeddings[batch_start : batch_start + batch_size]
        upserted = upsert_chunks(batch_chunks, batch_embeddings)
        indexed += upserted
        log.debug(
            "ChromaDB batch upserted",
            batch_start=batch_start,
            batch_size=len(batch_chunks),
            upserted=upserted,
        )

    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    log.info(
        "Embedding complete",
        document_id=document_id,
        new_chunks_indexed=indexed,
        skipped_chunks=skipped,
        total_chunks=total,
        latency_ms=latency_ms,
        model=embedding_provider.model,
    )

    return EmbeddingResult(
        document_id=document_id,
        total_chunks=total,
        new_chunks_indexed=indexed,
        skipped_chunks=skipped,
        embedding_model=embedding_provider.model,
        latency_ms=latency_ms,
    )
