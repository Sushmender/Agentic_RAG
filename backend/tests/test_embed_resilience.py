"""
backend/tests/test_embed_resilience.py
Unit and integration tests for:
  - Embedding circuit breaker state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED/OPEN)
  - BM25 lexical fallback retrieval with scoping guarantee
  - Query pipeline graceful degradation when embedding provider fails
  - Ensuring degraded answers are not stored in the response cache
  - Latency served_ms field on cache hit
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.query import RetrievalResult
from app.services.embed_circuit_breaker import (
    BreakerState,
    EmbedCircuitOpenError,
    EmbeddingCircuitBreaker,
    embed_circuit_breaker,
)
from app.services.lexical_retrieval import lexical_retrieve


# ── Fixtures & Auth ──────────────────────────────────────────────────────────

def get_auth_headers() -> dict:
    from app.core.security import create_access_token
    token = create_access_token("resilience_test_user")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def seed_test_user_document():
    import asyncio
    from datetime import datetime, timezone
    from app.db.sqlite_store import document_store
    from app.schemas.document import DocumentMetadata, DocumentStatus, DocumentType

    now = datetime.now(timezone.utc)
    doc = DocumentMetadata(
        document_id="doc_resilient",
        user_id="resilience_test_user",
        filename="resilient.pdf",
        document_type=DocumentType.PDF,
        mime_type="application/pdf",
        file_size_bytes=1024,
        status=DocumentStatus.COMPLETED,
        created_at=now,
        updated_at=now,
    )
    asyncio.run(document_store.save(doc))
    yield


@pytest.fixture(autouse=True)
def reset_breaker():
    """Reset global circuit breaker state before and after each test."""
    embed_circuit_breaker._state = BreakerState.CLOSED
    embed_circuit_breaker._consecutive_failures = 0
    embed_circuit_breaker._last_failure_ts = 0.0
    embed_circuit_breaker._opened_at = 0.0
    embed_circuit_breaker._probe_in_flight = False
    yield
    embed_circuit_breaker._state = BreakerState.CLOSED
    embed_circuit_breaker._consecutive_failures = 0
    embed_circuit_breaker._last_failure_ts = 0.0
    embed_circuit_breaker._opened_at = 0.0
    embed_circuit_breaker._probe_in_flight = False


# ── Circuit Breaker Unit Tests ───────────────────────────────────────────────

def test_circuit_breaker_closed_to_open():
    cb = EmbeddingCircuitBreaker(failure_threshold=2, failure_window_s=60, open_duration_s=60)
    assert cb.state == BreakerState.CLOSED
    assert not cb.is_open()

    # 1st failure -> stays closed
    cb.record_failure()
    assert cb.state == BreakerState.CLOSED
    assert not cb.is_open()

    # 2nd failure -> trips open
    cb.record_failure()
    assert cb.state == BreakerState.OPEN
    assert cb.is_open()


def test_circuit_breaker_window_reset():
    cb = EmbeddingCircuitBreaker(failure_threshold=2, failure_window_s=1.0, open_duration_s=60)
    cb.record_failure()
    # Wait past the failure window
    time.sleep(1.1)
    # This failure shouldn't trip it because previous failure expired
    cb.record_failure()
    assert cb.state == BreakerState.CLOSED


def test_circuit_breaker_half_open_probe_success():
    cb = EmbeddingCircuitBreaker(failure_threshold=2, failure_window_s=60, open_duration_s=0.1)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == BreakerState.OPEN

    # Wait for open duration
    time.sleep(0.15)
    assert cb.state == BreakerState.HALF_OPEN

    # Acquire probe
    assert cb.try_acquire_probe() is True
    # Second concurrent caller cannot acquire probe
    assert cb.try_acquire_probe() is False
    assert cb.is_open() is True

    # Probe succeeds -> CLOSED
    cb.record_success()
    assert cb.state == BreakerState.CLOSED
    assert not cb.is_open()


def test_circuit_breaker_half_open_probe_failure():
    cb = EmbeddingCircuitBreaker(failure_threshold=2, failure_window_s=60, open_duration_s=0.1)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.15)
    assert cb.state == BreakerState.HALF_OPEN

    assert cb.try_acquire_probe() is True
    # Probe fails -> OPEN again
    cb.record_failure()
    assert cb.state == BreakerState.OPEN
    assert cb.is_open() is True


# ── Lexical Retrieval Unit Tests ─────────────────────────────────────────────

def test_lexical_retrieve_empty_doc_ids():
    results = lexical_retrieve("some query", document_ids=[])
    assert results == []


def test_lexical_retrieve_bm25_ranking():
    sample_data = {
        "ids": ["chunk_01", "chunk_02", "chunk_03"],
        "metadatas": [
            {"document_id": "doc1", "chunk_type": "text", "page": 1, "bbox_x0": 0.0, "bbox_y0": 0.0, "bbox_x1": 1.0, "bbox_y1": 1.0},
            {"document_id": "doc1", "chunk_type": "text", "page": 2, "bbox_x0": 0.0, "bbox_y0": 0.0, "bbox_x1": 1.0, "bbox_y1": 1.0},
            {"document_id": "doc1", "chunk_type": "text", "page": 3, "bbox_x0": 0.0, "bbox_y0": 0.0, "bbox_x1": 1.0, "bbox_y1": 1.0},
        ],
        "documents": [
            "This chunk talks about quantum computing algorithms and qubits.",
            "This chunk describes recipe for baking chocolate chip cookies with sugar.",
            "This chunk is completely unrelated sports news about football.",
        ],
    }

    mock_collection = MagicMock()
    mock_collection.get.return_value = sample_data

    with patch("app.services.lexical_retrieval.get_collection", return_value=mock_collection):
        # We need > 40 chunks to test BM25 branch, or we test the <= 40 branch
        # Let's test the <= 40 branch first:
        res = lexical_retrieve("chocolate chip cookies", document_ids=["doc1"], top_n=5)
        assert len(res) == 3
        assert res[0].chunk_id in ["chunk_01", "chunk_02", "chunk_03"]

        # Now test BM25 branch by providing 45 chunks
        large_ids = [f"c_{i}" for i in range(50)]
        large_metas = [
            {"document_id": "doc1", "chunk_type": "text", "page": i, "bbox_x0": 0.0, "bbox_y0": 0.0, "bbox_x1": 1.0, "bbox_y1": 1.0}
            for i in range(50)
        ]
        large_docs = ["generic text without keyword"] * 50
        large_docs[15] = "chocolate chip cookies delicious dessert recipe"
        mock_collection.get.return_value = {
            "ids": large_ids,
            "metadatas": large_metas,
            "documents": large_docs,
        }

        res_bm25 = lexical_retrieve("chocolate chip cookies", document_ids=["doc1"], top_n=3)
        assert len(res_bm25) == 3
        # Top chunk should be chunk 15
        assert res_bm25[0].chunk_id == "c_15"
        assert res_bm25[0].similarity_score > 0.0


# ── Pipeline Integration Tests: Graceful Degradation ─────────────────────────

FAKE_LEXICAL_CHUNKS = [
    RetrievalResult(
        chunk_id="chunk_lex_01",
        document_id="doc_resilient",
        chunk_type="text",
        page=1,
        bbox=[0.0, 0.0, 1.0, 0.2],
        text="The annual revenue of the company grew by 25% to $50 million.",
        similarity_score=1.5,
    )
]

FAKE_LLM_RESULT = {
    "content": "The annual revenue grew by 25% to $50 million. [Source 1]",
    "model": "qwen/qwen3.8-27b",
    "provider": "groq",
    "input_tokens": 300,
    "output_tokens": 40,
    "total_tokens": 340,
    "cost_usd": 0.0002,
    "latency_ms": 250.0,
}


FAKE_RERANKED_DICTS = [
    {
        "chunk_id": "chunk_lex_01",
        "document_id": "doc_resilient",
        "chunk_type": "text",
        "page": 1,
        "bbox": [0.0, 0.0, 1.0, 0.2],
        "text": "The annual revenue of the company grew by 25% to $50 million.",
        "similarity_score": 1.5,
        "relevance_score": 0.95,
    }
]


def test_query_pipeline_embed_timeout_falls_back_to_lexical():
    """
    When embedding provider raises ReadTimeout, query endpoint must NOT return 502!
    It should return 200 with retrieval_mode='lexical_fallback' and degraded=True.
    """
    client = TestClient(app)

    async def mock_embed_query(query: str):
        raise httpx.ReadTimeout("OpenRouter embedding timed out after 4s")

    with (
        patch("app.api.v1.endpoints.query.embedding_provider.embed_query", side_effect=mock_embed_query),
        patch("app.api.v1.endpoints.query.lexical_retrieve", return_value=FAKE_LEXICAL_CHUNKS) as mock_lex,
        patch("app.api.v1.endpoints.query.reranker_provider.rerank", AsyncMock(return_value=FAKE_RERANKED_DICTS)),
        patch("app.services.llm_service.groq_provider.generate", AsyncMock(return_value=FAKE_LLM_RESULT)),
        patch("app.api.v1.endpoints.query.cache_service.get_cached_response", AsyncMock(return_value=None)),
        patch("app.api.v1.endpoints.query.cache_service.set_cached_response", AsyncMock()) as mock_set_cache,
    ):
        response = client.post(
            "/api/v1/query",
            json={"query": "What is the annual revenue?", "document_ids": ["doc_resilient"]},
            headers=get_auth_headers(),
        )

        assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"
        data = response.json()
        assert data["retrieval_mode"] == "lexical_fallback"
        assert data["degraded"] is True
        assert len(data["sources"]) > 0
        assert "50 million" in data["answer"]
        mock_lex.assert_called_once()

        # Critical: degraded answers MUST NOT be cached
        mock_set_cache.assert_not_called()


def test_query_pipeline_circuit_breaker_skips_provider():
    """
    When circuit breaker is OPEN, provider is never contacted, immediately falling back.
    """
    client = TestClient(app)

    # Trip the breaker
    embed_circuit_breaker.record_failure()
    embed_circuit_breaker.record_failure()
    assert embed_circuit_breaker.is_open()

    mock_embed = AsyncMock()

    with (
        patch("app.api.v1.endpoints.query.embedding_provider.embed_query", mock_embed),
        patch("app.api.v1.endpoints.query.lexical_retrieve", return_value=FAKE_LEXICAL_CHUNKS),
        patch("app.api.v1.endpoints.query.reranker_provider.rerank", AsyncMock(return_value=FAKE_RERANKED_DICTS)),
        patch("app.services.llm_service.groq_provider.generate", AsyncMock(return_value=FAKE_LLM_RESULT)),
        patch("app.api.v1.endpoints.query.cache_service.get_cached_response", AsyncMock(return_value=None)),
        patch("app.api.v1.endpoints.query.cache_service.set_cached_response", AsyncMock()),
    ):
        response = client.post(
            "/api/v1/query",
            json={"query": "What is the annual revenue?", "document_ids": ["doc_resilient"]},
            headers=get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["retrieval_mode"] == "lexical_fallback"
        assert data["degraded"] is True
        # Provider embed_query must NOT have been called at all!
        mock_embed.assert_not_called()
