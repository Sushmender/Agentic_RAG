"""
backend/tests/test_query_pipeline.py
Integration tests for the complete Day 5 query pipeline.

Tests:
  - Full pipeline: route → embed → retrieve → rerank → assemble → generate
  - Reranker failure → graceful fallback to raw retrieval order
  - Groq failure → automatic fallback to OpenRouter
  - Sources populated with correct schema fields
  - Latency fields all present and non-negative
  - llm_provider selector routes correctly (groq / openrouter)
  - Empty retrieval returns informative message without error

All external providers (embedding, reranker, LLM) are mocked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.query import RetrievalResult


# ── Shared mock data ──────────────────────────────────────────────────────────

FAKE_EMBEDDING = [0.1] * 64
FAKE_QUERY = "What is the total revenue?"

FAKE_CANDIDATES = [
    RetrievalResult(
        chunk_id=f"chunk_{i:03d}",
        document_id="doc_abc123",
        chunk_type="text",
        page=i,
        bbox=[0.0, 0.0, 1.0, 0.2],
        text=f"Revenue for Q{i} was $100M. This is source text chunk {i}.",
        similarity_score=0.9 - i * 0.05,
    )
    for i in range(5)
]

FAKE_RERANKED_DICTS = [
    {
        "chunk_id": f"chunk_{i:03d}",
        "document_id": "doc_abc123",
        "chunk_type": "text",
        "page": i,
        "bbox": [0.0, 0.0, 1.0, 0.2],
        "text": f"Revenue for Q{i} was $100M. This is source text chunk {i}.",
        "similarity_score": 0.9 - i * 0.05,
        "relevance_score": 0.95 - i * 0.05,
    }
    for i in range(3)  # Top-3 after reranking
]

FAKE_LLM_RESPONSE_GROQ = {
    "content": "Total revenue was $100M based on the provided evidence. [Source 1]",
    "model": "qwen/qwen3.8-27b",
    "provider": "groq",
    "input_tokens": 512,
    "output_tokens": 48,
    "total_tokens": 560,
    "cost_usd": 0.0003,
    "latency_ms": 350.0,
}

FAKE_LLM_RESPONSE_OPENROUTER = {
    "content": "The total revenue is $100M per source evidence. [Source 1]",
    "model": "nvidia/nemotron-3-super-120b-a12b:free",
    "provider": "openrouter",
    "input_tokens": 520,
    "output_tokens": 45,
    "total_tokens": 565,
    "cost_usd": 0.0,
    "latency_ms": 1200.0,
}


# ── Auth helper ───────────────────────────────────────────────────────────────

def get_auth_headers() -> dict:
    """Generate a valid JWT bearer token for test user."""
    from app.core.security import create_access_token
    token = create_access_token("test_user_001")
    return {"Authorization": f"Bearer {token}"}


# ── Shared patch context ──────────────────────────────────────────────────────

def make_all_patches(
    embed_result=None,
    retrieval_result=None,
    rerank_result=None,
    groq_result=None,
    rerank_raises=None,
    groq_raises=None,
):
    """
    Return a dict of active mocks after entering all necessary patches.
    Caller must use the returned context manager correctly.

    NOTE: This uses patch.multiple via individual patch() calls composed
    inside a single unittest.mock.patch context stack via start/stop.
    """
    embed_result = embed_result if embed_result is not None else FAKE_EMBEDDING
    retrieval_result = retrieval_result if retrieval_result is not None else FAKE_CANDIDATES
    rerank_result = rerank_result if rerank_result is not None else FAKE_RERANKED_DICTS
    groq_result = groq_result or FAKE_LLM_RESPONSE_GROQ

    # Build patchers
    patchers = [
        patch(
            "app.api.v1.endpoints.query.embedding_provider.embed_query",
            AsyncMock(return_value=embed_result),
        ),
        patch(
            "app.api.v1.endpoints.query.retrieve_text",
            MagicMock(return_value=retrieval_result),
        ),
        patch(
            "app.api.v1.endpoints.query.retrieve_multimodal",
            MagicMock(return_value=retrieval_result),
        ),
        patch(
            "app.api.v1.endpoints.query.retrieve_hybrid",
            MagicMock(return_value=retrieval_result),
        ),
        patch(
            "app.api.v1.endpoints.query.reranker_provider.rerank",
            AsyncMock(side_effect=rerank_raises) if rerank_raises
            else AsyncMock(return_value=rerank_result),
        ),
        patch(
            "app.services.llm_service.groq_provider.generate",
            AsyncMock(side_effect=groq_raises) if groq_raises
            else AsyncMock(return_value=groq_result),
        ),
        patch(
            "app.services.llm_service.openrouter_llm_provider.generate",
            AsyncMock(return_value=FAKE_LLM_RESPONSE_OPENROUTER),
        ),
    ]
    return patchers


@pytest.fixture()
def auth_headers():
    return get_auth_headers()


@pytest.fixture()
def api_client():
    """TestClient that starts/stops app lifespan properly."""
    with TestClient(app) as c:
        yield c


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFullPipeline:
    """Happy-path: full pipeline returns grounded answer."""

    def _query(self, payload=None):
        patchers = make_all_patches()
        mocks = [p.start() for p in patchers]
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/query",
                    json=payload or {"query": FAKE_QUERY},
                    headers=get_auth_headers(),
                )
        finally:
            for p in patchers:
                p.stop()
        return resp

    def test_query_returns_200_with_answer(self):
        resp = self._query()
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "answer" in data
        assert len(data["answer"]) > 10
        assert data["model_used"] != ""
        assert data["provider_used"] in ("groq", "openrouter")

    def test_response_schema_complete(self):
        resp = self._query()
        data = resp.json()
        required = ["answer", "sources", "route_type", "cache_hit",
                    "model_used", "provider_used", "latency", "token_usage", "cost_usd"]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_latency_fields_all_present(self):
        resp = self._query()
        latency = resp.json()["latency"]
        for key in ["total_ms", "cache_check_ms", "query_embed_ms",
                    "retrieval_ms", "reranking_ms", "llm_ms"]:
            assert key in latency, f"Missing latency field: {key}"
            assert latency[key] >= 0, f"Negative latency: {key}"

    def test_sources_have_correct_schema(self):
        resp = self._query()
        sources = resp.json()["sources"]
        assert len(sources) > 0, "Expected at least one source"
        for src in sources:
            for field in ["document_id", "chunk_id", "page", "bbox", "chunk_type"]:
                assert field in src, f"Source missing field: {field}"

    def test_token_usage_populated(self):
        resp = self._query()
        token_usage = resp.json()["token_usage"]
        assert token_usage.get("input_tokens", 0) > 0
        assert token_usage.get("output_tokens", 0) > 0
        assert token_usage.get("total_tokens", 0) > 0

    def test_route_type_in_response(self):
        resp = self._query()
        assert resp.json()["route_type"] in ("text", "multimodal", "hybrid")

    def test_cache_hit_false_on_fresh_query(self):
        resp = self._query()
        assert resp.json()["cache_hit"] is False


class TestProviderSelection:
    """llm_provider field routes to correct provider."""

    def _query_with_provider(self, provider: str, groq_raises=None):
        patchers = make_all_patches(groq_raises=groq_raises)
        [p.start() for p in patchers]
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/query",
                    json={"query": FAKE_QUERY, "llm_provider": provider},
                    headers=get_auth_headers(),
                )
        finally:
            for p in patchers:
                p.stop()
        return resp

    def test_groq_provider_used_by_default(self):
        resp = self._query_with_provider("groq")
        assert resp.status_code == 200, resp.text
        assert resp.json()["provider_used"] == "groq"
        assert resp.json()["model_used"] == "qwen/qwen3.8-27b"

    def test_openrouter_provider_selected(self):
        resp = self._query_with_provider("openrouter")
        assert resp.status_code == 200, resp.text
        # User explicitly chose openrouter — Groq skipped entirely
        assert resp.json()["provider_used"] == "openrouter"

    def test_openrouter_model_name_in_response(self):
        resp = self._query_with_provider("openrouter")
        assert "nemotron" in resp.json()["model_used"].lower()


class TestRerankerFailure:
    """Reranker fails → answer still generated using raw retrieval order."""

    def _query_with_reranker_failure(self, exc):
        patchers = make_all_patches(rerank_raises=exc)
        [p.start() for p in patchers]
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/query",
                    json={"query": FAKE_QUERY},
                    headers=get_auth_headers(),
                )
        finally:
            for p in patchers:
                p.stop()
        return resp

    def test_reranker_failure_does_not_break_pipeline(self):
        resp = self._query_with_reranker_failure(RuntimeError("Reranker API timeout"))
        assert resp.status_code == 200, resp.text

    def test_reranker_failure_answer_still_grounded(self):
        resp = self._query_with_reranker_failure(ConnectionError("Reranker unreachable"))
        data = resp.json()
        assert len(data["answer"]) > 10
        assert data["model_used"] != ""

    def test_reranker_failure_still_returns_sources(self):
        resp = self._query_with_reranker_failure(RuntimeError("Reranker down"))
        assert len(resp.json()["sources"]) > 0


class TestGroqFallback:
    """Groq fails → automatic fallback to OpenRouter, answer still returned."""

    def _query_with_groq_failure(self, exc):
        patchers = make_all_patches(groq_raises=exc)
        [p.start() for p in patchers]
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/query",
                    json={"query": FAKE_QUERY},
                    headers=get_auth_headers(),
                )
        finally:
            for p in patchers:
                p.stop()
        return resp

    def test_groq_failure_triggers_openrouter_fallback(self):
        resp = self._query_with_groq_failure(RuntimeError("Groq API key invalid"))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["provider_used"] == "openrouter"
        assert "nemotron" in data["model_used"].lower()
        assert len(data["answer"]) > 10

    def test_groq_timeout_falls_back_to_openrouter(self):
        import asyncio
        resp = self._query_with_groq_failure(asyncio.TimeoutError())
        assert resp.status_code == 200
        assert resp.json()["provider_used"] == "openrouter"

    def test_groq_http_error_falls_back_to_openrouter(self):
        import httpx
        request = httpx.Request("POST", "https://api.groq.com")
        response = httpx.Response(429, request=request)
        exc = httpx.HTTPStatusError("rate limit", request=request, response=response)
        resp = self._query_with_groq_failure(exc)
        assert resp.status_code == 200
        assert resp.json()["provider_used"] == "openrouter"


class TestEmptyRetrieval:
    """No chunks found → 200 with informative message, no sources."""

    def test_empty_retrieval_returns_200(self):
        patchers = make_all_patches(retrieval_result=[])
        [p.start() for p in patchers]
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/query",
                    json={"query": "xyzzy undefined query"},
                    headers=get_auth_headers(),
                )
        finally:
            for p in patchers:
                p.stop()
        assert resp.status_code == 200
        data = resp.json()
        assert data["sources"] == []
        assert len(data["answer"]) > 5

    def test_empty_retrieval_informative_message(self):
        patchers = make_all_patches(retrieval_result=[])
        [p.start() for p in patchers]
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/query",
                    json={"query": "some query with no results"},
                    headers=get_auth_headers(),
                )
        finally:
            for p in patchers:
                p.stop()
        answer = resp.json()["answer"].lower()
        # Should mention no content found or similar
        assert any(kw in answer for kw in ["no relevant", "not found", "no matching", "no content"])


class TestRerankerTopK:
    """Reranker called with correct candidate count, returns ≤ top_k."""

    def test_reranker_called_with_candidates_and_returns_correct_sources(self):
        mock_rerank = AsyncMock(return_value=FAKE_RERANKED_DICTS[:3])

        patchers = [
            patch("app.api.v1.endpoints.query.embedding_provider.embed_query",
                  AsyncMock(return_value=FAKE_EMBEDDING)),
            patch("app.api.v1.endpoints.query.retrieve_text",
                  MagicMock(return_value=FAKE_CANDIDATES)),
            patch("app.api.v1.endpoints.query.retrieve_multimodal",
                  MagicMock(return_value=FAKE_CANDIDATES)),
            patch("app.api.v1.endpoints.query.retrieve_hybrid",
                  MagicMock(return_value=FAKE_CANDIDATES)),
            patch("app.api.v1.endpoints.query.reranker_provider.rerank", mock_rerank),
            patch("app.services.llm_service.groq_provider.generate",
                  AsyncMock(return_value=FAKE_LLM_RESPONSE_GROQ)),
            patch("app.services.llm_service.openrouter_llm_provider.generate",
                  AsyncMock(return_value=FAKE_LLM_RESPONSE_OPENROUTER)),
        ]
        [p.start() for p in patchers]
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/v1/query",
                    json={"query": FAKE_QUERY},
                    headers=get_auth_headers(),
                )
        finally:
            for p in patchers:
                p.stop()

        assert resp.status_code == 200, resp.text
        # Reranker was called once
        mock_rerank.assert_called_once()
        # Candidates passed to reranker ≤ 20 (DEFAULT_TOP_N)
        call_kwargs = mock_rerank.call_args.kwargs
        candidates_passed = call_kwargs.get("candidates", [])
        assert len(candidates_passed) <= 20
        # Sources in response ≤ top_k (default 5)
        assert len(resp.json()["sources"]) <= 5


class TestInputValidation:
    """Query request validation."""

    def test_empty_query_rejected(self):
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/query",
                json={"query": ""},
                headers=get_auth_headers(),
            )
        assert resp.status_code == 422  # Validation error

    def test_missing_auth_rejected(self):
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/query",
                json={"query": FAKE_QUERY},
            )
        assert resp.status_code == 401
