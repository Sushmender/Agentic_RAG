"""
backend/tests/test_embed_consistency.py
Unit tests for embedding consistency checks, ChromaDB metadata guards,
startup/query warning logs, and health endpoint response.

All tests are mocked with NO network calls.
"""
from __future__ import annotations

import chromadb
import pytest

from app.api.v1.endpoints import health
from app.core.config import get_settings
from app.db import chromadb_client
from app.schemas.chunk import Chunk, ChunkType
from scripts.check_embed_consistency import (
    calculate_cosine_similarity,
    get_verdict,
)


@pytest.fixture(autouse=True)
def ephemeral_chroma(monkeypatch):
    """Use an isolated in-memory ephemeral ChromaDB client for each test."""
    client = chromadb.EphemeralClient()
    monkeypatch.setattr(chromadb_client, "_chroma_client", client)
    monkeypatch.setattr(chromadb_client, "_collection", None)
    chromadb_client.init_chromadb(client=client)
    yield client
    try:
        client.delete_collection(chromadb_client.settings.CHROMA_COLLECTION_NAME)
    except Exception:
        pass
    monkeypatch.setattr(chromadb_client, "_collection", None)
    monkeypatch.setattr(chromadb_client, "_chroma_client", None)


def _make_sample_chunk(chunk_id: str, doc_id: str, text: str = "sample text") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        chunk_type=ChunkType.TEXT,
        text=text,
        page=0,
        bbox=[0.0, 0.0, 1.0, 1.0],
        source="test.pdf",
        parser_version="1.0",
    )


class DummyAwaitable:
    """Synchronously resolving awaitable for non-blocking mocked async calls."""
    def __init__(self, value=True):
        self._value = value

    def __await__(self):
        if False:
            yield
        return self._value


# ── 1. Metadata Storage on Ingestion ──────────────────────────────────────────

def test_upsert_stores_embedding_model_in_collection_and_chunks():
    """Verify upsert_chunks stores the embedding model in both collection and chunk metadata."""
    chunk = _make_sample_chunk("c1", "doc1")
    embedding = [0.1, 0.2, 0.3, 0.4]

    custom_model = "test-provider/test-embed-v1"
    chromadb_client.upsert_chunks([chunk], [embedding], embedding_model=custom_model)

    col = chromadb_client.get_collection()
    # Check collection metadata
    assert col.metadata.get("embedding_model") == custom_model

    # Check chunk metadata
    res = col.get(ids=["c1"], include=["metadatas"])
    assert res["metadatas"][0].get("embedding_model") == custom_model


def test_upsert_defaults_to_settings_model():
    """When embedding_model is not explicitly passed, it defaults to settings.EMBEDDING_MODEL."""
    settings = get_settings()
    chunk = _make_sample_chunk("c2", "doc2")
    embedding = [0.5, 0.6, 0.7, 0.8]

    chromadb_client.upsert_chunks([chunk], [embedding])

    col = chromadb_client.get_collection()
    assert col.metadata.get("embedding_model") == settings.EMBEDDING_MODEL
    res = col.get(ids=["c2"], include=["metadatas"])
    assert res["metadatas"][0].get("embedding_model") == settings.EMBEDDING_MODEL


# ── 2. Guard: check_embedding_model_mismatch ───────────────────────────────────

def test_check_embedding_model_mismatch_false_when_matching():
    """Returns False when stored model matches current settings."""
    settings = get_settings()
    chunk = _make_sample_chunk("c1", "doc1")
    chromadb_client.upsert_chunks([chunk], [[1.0, 0.0]], embedding_model=settings.EMBEDDING_MODEL)

    assert chromadb_client.check_embedding_model_mismatch() is False


def test_check_embedding_model_mismatch_true_when_different():
    """Returns True when stored model differs from current settings."""
    chunk = _make_sample_chunk("c1", "doc1")
    chromadb_client.upsert_chunks([chunk], [[1.0, 0.0]], embedding_model="legacy-model-v0")

    assert chromadb_client.check_embedding_model_mismatch() is True


def test_check_embedding_model_mismatch_none_when_empty():
    """Returns None when collection has no stored model and 0 chunks."""
    col = chromadb_client.get_collection()
    # Modify metadata to clear embedding_model
    col.modify(metadata={"cleared": "true"})
    assert col.count() == 0
    assert chromadb_client.check_embedding_model_mismatch() is None


# ── 3. Warnings at Startup and Query ───────────────────────────────────────────

def test_query_similar_logs_warning_on_model_mismatch(capsys, caplog):
    """query_similar logs a structlog warning when stored model differs from query model."""
    chunk = _make_sample_chunk("c1", "doc1")
    chromadb_client.upsert_chunks([chunk], [[1.0, 0.0]], embedding_model="different/model:v1")

    chromadb_client.query_similar(embedding=[1.0, 0.0], n_results=1)
    captured = capsys.readouterr()
    assert "Embedding model mismatch" in captured.out or "Embedding model mismatch" in caplog.text or any("Embedding model mismatch" in str(r.message) for r in caplog.records)


# ── 4. Health Endpoint ────────────────────────────────────────────────────────

def test_health_check_reports_model_mismatch_false(monkeypatch):
    """Health check endpoint response contains embedding_model_mismatch=False when models match."""
    monkeypatch.setattr(health.chromadb_client, "is_healthy", lambda: True)
    monkeypatch.setattr(health.redis_client, "is_healthy", lambda: DummyAwaitable(True))
    monkeypatch.setattr(health.chromadb_client, "check_embedding_model_mismatch", lambda: False)

    coro = health.health_check()
    try:
        coro.send(None)
    except StopIteration as exc:
        res = exc.value
        assert res["status"] == "ok"
        assert res.get("embedding_model_mismatch") is False


def test_health_check_reports_model_mismatch_true(monkeypatch):
    """Health check endpoint response contains embedding_model_mismatch=True when models mismatch."""
    monkeypatch.setattr(health.chromadb_client, "is_healthy", lambda: True)
    monkeypatch.setattr(health.redis_client, "is_healthy", lambda: DummyAwaitable(True))
    monkeypatch.setattr(health.chromadb_client, "check_embedding_model_mismatch", lambda: True)

    coro = health.health_check()
    try:
        coro.send(None)
    except StopIteration as exc:
        res = exc.value
        assert res["status"] == "ok"
        assert res.get("embedding_model_mismatch") is True


# ── 5. Script Math & Verdict Logic ────────────────────────────────────────────

def test_cosine_similarity_calculation():
    """Verify cosine similarity calculation edge cases and accuracy."""
    # Identical vectors -> 1.0
    v1 = [1.0, 2.0, 3.0]
    assert pytest.approx(calculate_cosine_similarity(v1, v1), 1e-6) == 1.0

    # Orthogonal vectors -> 0.0
    v2 = [1.0, 0.0]
    v3 = [0.0, 1.0]
    assert calculate_cosine_similarity(v2, v3) == 0.0

    # Opposite vectors -> -1.0
    v4 = [1.0, 0.0]
    v5 = [-1.0, 0.0]
    assert pytest.approx(calculate_cosine_similarity(v4, v5), 1e-6) == -1.0

    # Dimension mismatch -> 0.0
    assert calculate_cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


def test_verdict_thresholds():
    """Verify above 0.99 is consistent and 0.99 or below is MISMATCH."""
    assert get_verdict(0.995, dim_match=True) == "consistent"
    assert get_verdict(0.991, dim_match=True) == "consistent"
    assert "MISMATCH" in get_verdict(0.990, dim_match=True)
    assert "MISMATCH" in get_verdict(0.950, dim_match=True)
    assert "MISMATCH" in get_verdict(0.80, dim_match=True)

    # Dimension mismatch overrides similarity score
    assert "MISMATCH" in get_verdict(0.999, dim_match=False)


def test_ensure_collection_metadata_model_writes_missing():
    """Startup guard writes collection-level model name when missing without touching vectors."""
    chunk = _make_sample_chunk("c1", "doc1")
    chromadb_client.upsert_chunks([chunk], [[1.0, 0.0]], embedding_model="custom/test-model:v1")

    col = chromadb_client.get_collection()
    # Strip embedding_model from collection metadata to simulate legacy state (exclude hnsw:space)
    col.modify(metadata={"legacy_unmarked": "true"})
    assert col.metadata.get("embedding_model") is None

    # Run startup guard
    written = chromadb_client.ensure_collection_metadata_model()
    assert written == "custom/test-model:v1"

    # Verify collection metadata now records it
    assert chromadb_client.get_collection().metadata.get("embedding_model") == "custom/test-model:v1"
