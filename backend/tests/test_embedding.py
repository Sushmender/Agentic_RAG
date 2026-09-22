"""
backend/tests/test_embedding.py
Day 3 — Embedding + ChromaDB indexing tests (all mocked, no real API calls).

Tests:
  1. test_embed_passages_batching          — verifies batching logic splits into correct groups
  2. test_embed_query_single_vector        — embed_query() returns a single vector
  3. test_chromadb_upsert_idempotency      — same chunk_ids upserted twice → count stays same
  4. test_embedding_service_skips_existing — all chunks in ChromaDB → 0 new embeddings
  5. test_embedding_service_new_chunks     — no chunks in ChromaDB → all indexed
  6. test_get_chunk_by_id                  — upsert then get → correct fields returned
  7. test_ingestion_pipeline_includes_embedding — full pipeline with mocked ADE + mocked embedding
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import chromadb
import pytest
import pytest_asyncio

from app.db.chromadb_client import (
    get_chunk_by_id,
    get_existing_ids,
    init_chromadb,
    upsert_chunks,
)
from app.schemas.chunk import Chunk, ChunkType


# ── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture
def ephemeral_chroma(monkeypatch):
    """
    Initialize ChromaDB with an in-memory EphemeralClient for each test.
    Uses a unique collection name per test to guarantee full isolation.
    Resets the module-level _chroma_client and _collection after each test.
    """
    import uuid
    import app.db.chromadb_client as chroma_module

    # Reset module state before
    chroma_module._chroma_client = None
    chroma_module._collection = None

    # Use a unique collection name so no test pollutes another
    unique_name = f"test_collection_{uuid.uuid4().hex[:8]}"
    original_name = chroma_module.settings.CHROMA_COLLECTION_NAME
    monkeypatch.setattr(chroma_module.settings, "CHROMA_COLLECTION_NAME", unique_name)

    client = chromadb.EphemeralClient()
    init_chromadb(client=client)

    yield client

    # Cleanup: reset state after test
    chroma_module._chroma_client = None
    chroma_module._collection = None


def _make_chunk(
    document_id: str = "doc123",
    chunk_type: ChunkType = ChunkType.TEXT,
    page: int = 0,
    suffix: str = "",
) -> Chunk:
    """Helper to build a deterministic test Chunk."""
    bbox = [0.1, 0.1, 0.9, 0.9]
    return Chunk(
        chunk_id=f"chunk_{suffix or uuid.uuid4().hex[:8]}",
        document_id=document_id,
        chunk_type=chunk_type,
        text=f"Sample text for chunk {suffix}",
        page=page,
        bbox=bbox,
        source="test.pdf",
        parser_version="dpt-2-test",
    )


def _fake_embeddings(count: int, dim: int = 8) -> list[list[float]]:
    """Produce deterministic fake embedding vectors for testing."""
    return [[float(i + j * 0.1) for j in range(dim)] for i in range(count)]


# ── Test 1: Batch splitting logic ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_embed_passages_batching():
    """
    embed_passages() should split N texts into ceil(N/batch_size) API calls.
    With 5 texts and batch_size=2 → 3 calls (2+2+1).
    """
    from app.providers.openrouter_embedding import OpenRouterEmbeddingProvider

    provider = OpenRouterEmbeddingProvider()
    call_count = 0
    batches_seen = []

    async def mock_call_with_retry(batch, input_type, log_context):
        nonlocal call_count
        call_count += 1
        batches_seen.append(len(batch))
        return _fake_embeddings(len(batch))

    with patch.object(provider, "_call_with_retry", side_effect=mock_call_with_retry):
        results = await provider.embed_passages(
            texts=["text1", "text2", "text3", "text4", "text5"],
            batch_size=2,
        )

    assert call_count == 3, f"Expected 3 batch calls, got {call_count}"
    assert batches_seen == [2, 2, 1], f"Unexpected batch sizes: {batches_seen}"
    assert len(results) == 5, "Should return one embedding per input text"
    assert all(len(v) == 8 for v in results), "Each embedding should have 8 dimensions"


# ── Test 2: embed_query returns single vector ──────────────────────────────────

@pytest.mark.asyncio
async def test_embed_query_single_vector():
    """embed_query() wraps single text, calls API once with input_type='query', returns 1D list."""
    from app.providers.openrouter_embedding import OpenRouterEmbeddingProvider

    provider = OpenRouterEmbeddingProvider()

    async def mock_call_with_retry(batch, input_type, log_context):
        assert input_type == "query", f"Expected 'query', got '{input_type}'"
        assert len(batch) == 1
        return _fake_embeddings(1)

    with patch.object(provider, "_call_with_retry", side_effect=mock_call_with_retry):
        result = await provider.embed_query("What is the revenue?")

    assert isinstance(result, list), "embed_query should return a flat list of floats"
    assert isinstance(result[0], float), "Embedding values should be floats"


# ── Test 3: ChromaDB upsert idempotency ───────────────────────────────────────

def test_chromadb_upsert_idempotency(ephemeral_chroma):
    """
    Upserting the same chunk_ids twice should NOT increase the collection count.
    ChromaDB upsert semantics: existing IDs are overwritten, not duplicated.
    """
    chunks = [_make_chunk(suffix=str(i)) for i in range(3)]
    embeddings = _fake_embeddings(3)

    count_1 = upsert_chunks(chunks, embeddings)
    count_2 = upsert_chunks(chunks, embeddings)  # same chunks again

    from app.db.chromadb_client import get_collection
    total = get_collection().count()

    assert count_1 == 3
    assert count_2 == 3
    assert total == 3, f"Expected 3 unique chunks, got {total}"


# ── Test 4: embedding_service skips existing chunks ────────────────────────────

@pytest.mark.asyncio
async def test_embedding_service_skips_existing(ephemeral_chroma, set_test_env, tmp_path):
    """
    If all chunk_ids are already in ChromaDB, index_chunks() should:
    - Return new_chunks_indexed=0
    - NOT call the embedding provider at all
    """
    from app.services import embedding_service

    doc_id = "test_doc_skip"
    chunks = [_make_chunk(document_id=doc_id, suffix=str(i)) for i in range(3)]
    embeddings = _fake_embeddings(3)

    # Pre-index all chunks
    upsert_chunks(chunks, embeddings)

    # Write chunks.json to temp ADE output dir
    ade_dir = Path(set_test_env["ade_out"]) / doc_id
    ade_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = ade_dir / "chunks.json"
    chunks_path.write_text(
        json.dumps([c.model_dump() for c in chunks]),
        encoding="utf-8",
    )

    # Patch provider to ensure it's NOT called
    mock_provider = MagicMock()
    mock_provider.embed_passages = AsyncMock(return_value=[])
    mock_provider.model = "test-model"

    with patch("app.services.embedding_service.embedding_provider", mock_provider):
        # Also patch the ADE_OUTPUT_DIR to point to temp dir
        with patch("app.services.embedding_service.settings") as mock_settings:
            mock_settings.ADE_OUTPUT_DIR = str(set_test_env["ade_out"])
            mock_settings.EMBEDDING_BATCH_SIZE = 16
            result = await embedding_service.index_chunks(doc_id)

    mock_provider.embed_passages.assert_not_called()
    assert result.new_chunks_indexed == 0
    assert result.skipped_chunks == 3


# ── Test 5: embedding_service indexes new chunks ───────────────────────────────

@pytest.mark.asyncio
async def test_embedding_service_new_chunks(ephemeral_chroma, set_test_env):
    """
    When no chunks are pre-indexed, index_chunks() should:
    - Call embed_passages() once with all texts
    - Return new_chunks_indexed == total chunk count
    - ChromaDB count == total chunk count
    """
    import app.db.chromadb_client as chroma_module
    from app.db.chromadb_client import get_collection
    from app.services import embedding_service

    doc_id = "test_doc_new"
    chunks = [_make_chunk(document_id=doc_id, suffix=str(i)) for i in range(3)]

    # Write chunks.json
    ade_dir = Path(set_test_env["ade_out"]) / doc_id
    ade_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = ade_dir / "chunks.json"
    chunks_path.write_text(
        json.dumps([c.model_dump() for c in chunks]),
        encoding="utf-8",
    )

    # Mock provider to return fake embeddings
    fake_embs = _fake_embeddings(3)
    mock_provider = MagicMock()
    mock_provider.embed_passages = AsyncMock(return_value=fake_embs)
    mock_provider.model = "nvidia/llama-nemotron-embed-vl-1b-v2:free"

    with patch("app.services.embedding_service.embedding_provider", mock_provider):
        with patch("app.services.embedding_service.settings") as mock_settings:
            mock_settings.ADE_OUTPUT_DIR = str(set_test_env["ade_out"])
            mock_settings.EMBEDDING_BATCH_SIZE = 16
            # Patch upsert_chunks to use the ephemeral collection from the fixture
            result = await embedding_service.index_chunks(doc_id)

    mock_provider.embed_passages.assert_called_once()
    assert result.new_chunks_indexed == 3
    assert result.skipped_chunks == 0
    assert result.total_chunks == 3
    # The ephemeral collection from our fixture is in use
    assert get_collection().count() == 3


# ── Test 6: get_chunk_by_id returns correct fields ────────────────────────────

def test_get_chunk_by_id(ephemeral_chroma):
    """
    After upserting a chunk, get_chunk_by_id() should return a dict
    with correct chunk_id, document_id, chunk_type, page, bbox, and text.
    """
    chunk = _make_chunk(
        document_id="doc_test_get",
        chunk_type=ChunkType.TABLE,
        page=2,
        suffix="abc",
    )
    embeddings = _fake_embeddings(1)
    upsert_chunks([chunk], embeddings)

    result = get_chunk_by_id(chunk.chunk_id)

    assert result is not None, "get_chunk_by_id should find the chunk"
    assert result["chunk_id"] == chunk.chunk_id
    assert result["document_id"] == "doc_test_get"
    assert result["chunk_type"] == "table"
    assert result["page"] == 2
    assert len(result["bbox"]) == 4
    assert result["text"] == chunk.text

    # Also verify a missing chunk returns None
    missing = get_chunk_by_id("nonexistent_chunk_id")
    assert missing is None


# ── Test 7: Full ingestion pipeline includes embedding ─────────────────────────

@pytest.mark.asyncio
async def test_ingestion_pipeline_includes_embedding(ephemeral_chroma, set_test_env):
    """
    The full ingestion pipeline (run_ingestion) should call index_chunks()
    after chunking, resulting in COMPLETED job + document with embedding_model set.
    ADE provider and embedding_service.index_chunks() are both mocked.
    """
    import uuid
    from app.db.in_memory_store import document_store, job_store
    from app.schemas.document import DocumentMetadata, DocumentStatus, DocumentType
    from app.schemas.job import Job, JobStatus
    from app.services import embedding_service
    from app.services.ingestion_service import run_ingestion

    doc_id = "pipeline_test_doc_" + uuid.uuid4().hex[:8]
    job_id = str(uuid.uuid4())
    user_id = "test_user"

    # Create a fake uploaded file
    upload_dir = Path(set_test_env["uploads"]) / doc_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    test_file = upload_dir / "test.pdf"
    test_file.write_bytes(b"%PDF-1.4 fake content")

    # Seed document + job records
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    document_store.save(DocumentMetadata(
        document_id=doc_id, filename="test.pdf", document_type=DocumentType.PDF,
        mime_type="application/pdf", file_size_bytes=100, user_id=user_id,
        status=DocumentStatus.PENDING, created_at=now, updated_at=now,
    ))
    job_store.save(Job(
        job_id=job_id, document_id=doc_id, user_id=user_id,
        status=JobStatus.PENDING, created_at=now, updated_at=now,
    ))

    # Mock ADE provider to return 2 fake chunks
    fake_ade_result = {
        "chunks": [
            {"id": "ade1", "type": "text", "markdown": "First chunk content",
             "grounding": {"box": {"left": 0.0, "top": 0.0, "right": 0.5, "bottom": 0.3}, "page": 0}},
            {"id": "ade2", "type": "text", "markdown": "Second chunk content",
             "grounding": {"box": {"left": 0.0, "top": 0.3, "right": 0.5, "bottom": 0.6}, "page": 0}},
        ],
        "markdown": "# Test\nFirst chunk content\nSecond chunk content",
        "metadata": {"version": "dpt-2-test", "credit_usage": 1.0, "page_count": 1},
        "grounding": {},
    }

    # Mock index_chunks() to return a fake EmbeddingResult — avoids path issues
    from app.services.embedding_service import EmbeddingResult
    fake_embedding_result = EmbeddingResult(
        document_id=doc_id,
        total_chunks=2,
        new_chunks_indexed=2,
        skipped_chunks=0,
        embedding_model="nvidia/llama-nemotron-embed-vl-1b-v2:free",
        latency_ms=50.0,
    )

    with patch("app.services.ingestion_service.ade_provider") as mock_ade:
        mock_ade.parse_document = AsyncMock(return_value=fake_ade_result)
        with patch.object(embedding_service, "index_chunks", AsyncMock(return_value=fake_embedding_result)):
            await run_ingestion(
                document_id=doc_id,
                job_id=job_id,
                file_path=str(test_file),
                user_id=user_id,
            )

    # Verify job reached COMPLETED
    job = job_store.get(job_id)
    assert job is not None
    assert job.status == JobStatus.COMPLETED, f"Job status: {job.status}, error: {job.error_message}"
    assert job.chunks_created == 2
    assert job.chunks_embedded == 2

    # Verify document marked COMPLETED with embedding_model
    doc = document_store.get(doc_id)
    assert doc is not None
    assert doc.status == DocumentStatus.COMPLETED
    assert doc.chunk_count == 2
    assert doc.embedding_model == "nvidia/llama-nemotron-embed-vl-1b-v2:free"

