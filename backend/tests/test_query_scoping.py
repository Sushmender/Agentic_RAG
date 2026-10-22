"""
backend/tests/test_query_scoping.py
Tests for cross-user isolation and ownership scoping in the query path.

Requirements tested:
1. Two users each with a document: user A's unfiltered query never returns user B's chunks.
2. Filtering by user B's document id as user A returns 404 ("Document not found").
3. A user with no documents gets the friendly response ("Upload a document to get started")
   and embedding, rerank, and LLM providers are never called.
4. Uploading or deleting a document changes the all-documents cache key.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db import chromadb_client
from app.db.sqlite_store import document_store
from app.main import app
from app.schemas.chunk import Chunk
from app.schemas.document import DocumentMetadata, DocumentStatus, DocumentType
from app.schemas.query import LatencyBreakdown, QueryResponse, RouteType
from app.services import cache_service


def _auth_headers(user_id: str) -> dict:
    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _seed_document(doc_id: str, user_id: str, filename: str = "test.pdf") -> DocumentMetadata:
    now = datetime.now(timezone.utc)
    doc = DocumentMetadata(
        document_id=doc_id,
        user_id=user_id,
        filename=filename,
        document_type=DocumentType.PDF,
        mime_type="application/pdf",
        file_size_bytes=2048,
        status=DocumentStatus.COMPLETED,
        created_at=now,
        updated_at=now,
    )
    asyncio.run(document_store.save(doc))
    return doc


async def _seed_document_async(doc_id: str, user_id: str, filename: str = "test.pdf") -> DocumentMetadata:
    now = datetime.now(timezone.utc)
    doc = DocumentMetadata(
        document_id=doc_id,
        user_id=user_id,
        filename=filename,
        document_type=DocumentType.PDF,
        mime_type="application/pdf",
        file_size_bytes=2048,
        status=DocumentStatus.COMPLETED,
        created_at=now,
        updated_at=now,
    )
    await document_store.save(doc)
    return doc


def _seed_chunk(chunk_id: str, doc_id: str, text: str, embedding: list[float]):
    chunk = Chunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        chunk_type="text",
        text=text,
        page=1,
        bbox=[0.0, 0.0, 1.0, 0.2],
        source="test.pdf",
        parser_version="v1",
    )
    chromadb_client.upsert_chunks([chunk], [embedding])


# ── Test 1: Cross-user chunk isolation ────────────────────────────────────────

def test_user_a_unfiltered_query_never_returns_user_b_chunks():
    """
    Two users each have a document in the store and chunks in ChromaDB.
    User A's unfiltered query must only retrieve chunks from User A's document,
    even if User B's chunk has a higher similarity score.
    """
    user_a = "user_alpha"
    user_b = "user_beta"

    doc_a = "doc_a_111"
    doc_b = "doc_b_222"

    _seed_document(doc_a, user_a, "alpha.pdf")
    _seed_document(doc_b, user_b, "beta.pdf")

    # Index chunks in ChromaDB: user B's chunk matches the embedding perfectly
    vec_match = [1.0] + [0.0] * 63
    vec_partial = [0.8] + [0.1] * 63

    _seed_chunk("chunk_a1", doc_a, "User A sensitive earnings details", vec_partial)
    _seed_chunk("chunk_b1", doc_b, "User B top secret financial data", vec_match)

    mock_llm_res = {
        "content": "Answer based on [Source 1]",
        "model": "qwen/qwen3.8-27b",
        "provider": "groq",
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "cost_usd": 0.0001,
        "latency_ms": 150.0,
    }

    with patch(
        "app.api.v1.endpoints.query.embedding_provider.embed_query",
        AsyncMock(return_value=vec_match),
    ), patch(
        "app.services.llm_service.groq_provider.generate",
        AsyncMock(return_value=mock_llm_res),
    ), patch(
        "app.services.cache_service.get_cached_response",
        AsyncMock(return_value=None),
    ), patch(
        "app.services.cache_service.set_cached_response",
        AsyncMock(return_value=None),
    ):
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/query",
                json={"query": "financial details"},
                headers=_auth_headers(user_a),
            )

    assert resp.status_code == 200, resp.text
    data = resp.json()

    # User A's sources must only contain doc_a, NEVER doc_b
    assert len(data["sources"]) > 0
    for src in data["sources"]:
        assert src["document_id"] == doc_a
        assert src["document_id"] != doc_b
        assert "User B" not in src["text_preview"]


# ── Test 2: Document ownership enforcement on query filter ────────────────────

def test_filter_by_user_b_document_as_user_a_returns_404():
    """
    Filtering by User B's document ID as User A must return 404 "Document not found"
    (same error as nonexistent doc, revealing no information about ownership).
    """
    user_a = "user_alpha_404"
    user_b = "user_beta_404"

    doc_a = "doc_owned_by_a"
    doc_b = "doc_owned_by_b"

    _seed_document(doc_a, user_a, "doc_a.pdf")
    _seed_document(doc_b, user_b, "doc_b.pdf")

    with TestClient(app) as client:
        # User A attempts to filter using User B's document
        resp = client.post(
            "/api/v1/query",
            json={"query": "Any query", "document_ids": [doc_b]},
            headers=_auth_headers(user_a),
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Document not found"

        # User A attempts to filter using one owned and one unowned document
        resp_mixed = client.post(
            "/api/v1/query",
            json={"query": "Any query", "document_ids": [doc_a, doc_b]},
            headers=_auth_headers(user_a),
        )
        assert resp_mixed.status_code == 404
        assert resp_mixed.json()["detail"] == "Document not found"

        # User A attempts to filter by a non-existent document ID
        resp_none = client.post(
            "/api/v1/query",
            json={"query": "Any query", "document_ids": ["non_existent_doc"]},
            headers=_auth_headers(user_a),
        )
        assert resp_none.status_code == 404
        assert resp_none.json()["detail"] == "Document not found"


# ── Test 3: User with no documents gets friendly response ─────────────────────

def test_user_with_no_documents_gets_friendly_response_without_calling_providers():
    """
    A caller with no documents must immediately receive a friendly response
    ("Upload a document to get started") with empty sources, and embedding,
    rerank, and LLM providers must NOT be called.
    """
    user_empty = "user_empty_docs"

    mock_embed = AsyncMock()
    mock_rerank = AsyncMock()
    mock_llm = AsyncMock()

    with patch("app.api.v1.endpoints.query.embedding_provider.embed_query", mock_embed), \
         patch("app.api.v1.endpoints.query.reranker_provider.rerank", mock_rerank), \
         patch("app.api.v1.endpoints.query.generate_answer", mock_llm):

        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/query",
                json={"query": "What is in my documents?"},
                headers=_auth_headers(user_empty),
            )

    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["answer"] == "Upload a document to get started"
    assert data["sources"] == []
    assert data["cache_hit"] is False

    # Verify NO external provider calls were made
    mock_embed.assert_not_called()
    mock_rerank.assert_not_called()
    mock_llm.assert_not_called()


# ── Test 4: Cache key changes on document upload or deletion ──────────────────

def test_cache_key_changes_on_document_upload_and_deletion():
    """
    Uploading or deleting a document must change the all-documents cache key,
    ensuring natural invalidation of cached queries.
    """
    from app.services.cache_service import _cache_key, _doc_key, compute_all_docs_hash

    user_id = "user_cache_test"

    # 1. User starts with 1 document
    initial_docs = ["doc_001"]
    key_initial = _cache_key(user_id, _doc_key(None, all_document_ids=initial_docs))
    assert key_initial == f"user:{user_id}:qa:__all__:{compute_all_docs_hash(initial_docs)}"

    # 2. User uploads a 2nd document
    uploaded_docs = ["doc_001", "doc_002"]
    key_after_upload = _cache_key(user_id, _doc_key(None, all_document_ids=uploaded_docs))
    assert key_after_upload == f"user:{user_id}:qa:__all__:{compute_all_docs_hash(uploaded_docs)}"

    # Cache key must change after upload
    assert key_initial != key_after_upload

    # 3. User deletes doc_001
    remaining_docs = ["doc_002"]
    key_after_delete = _cache_key(user_id, _doc_key(None, all_document_ids=remaining_docs))
    assert key_after_delete == f"user:{user_id}:qa:__all__:{compute_all_docs_hash(remaining_docs)}"

    # Cache key must change after deletion and not match previous keys
    assert key_after_delete != key_after_upload
    assert key_after_delete != key_initial


@pytest.mark.asyncio
async def test_cache_get_set_lifecycle_invalidates_on_document_changes():
    """
    Verify get_cached_response and set_cached_response naturally invalidate
    when caller's documents change in SQLite.
    """
    user_id = "user_cache_lifecycle"

    # Start with doc1
    await _seed_document_async("doc_live_1", user_id, "doc1.pdf")

    dummy_response = QueryResponse(
        answer="Cached answer about doc 1",
        sources=[],
        route_type=RouteType.TEXT,
        cache_hit=False,
        model_used="test-model",
        provider_used="groq",
        latency=LatencyBreakdown(),
        token_usage={},
        cost_usd=0.0,
    )

    query = "What is the summary?"

    # Set response in cache
    await cache_service.set_cached_response(
        user_id=user_id,
        document_ids=None,
        query=query,
        response=dummy_response,
    )

    # Retrieval should be a cache hit
    hit = await cache_service.get_cached_response(
        user_id=user_id,
        document_ids=None,
        query=query,
    )
    assert hit is not None
    assert hit.answer == "Cached answer about doc 1"
    assert hit.cache_hit is True

    # Upload doc2
    await _seed_document_async("doc_live_2", user_id, "doc2.pdf")

    # Retrieval for unfiltered query should now MISS cache because document set changed
    miss_after_upload = await cache_service.get_cached_response(
        user_id=user_id,
        document_ids=None,
        query=query,
    )
    assert miss_after_upload is None

    # Delete doc_live_1
    await document_store.delete("doc_live_1", user_id=user_id)

    # Retrieval should still miss cache because document set is now just doc_live_2
    miss_after_delete = await cache_service.get_cached_response(
        user_id=user_id,
        document_ids=None,
        query=query,
    )
    assert miss_after_delete is None
