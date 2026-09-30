"""
backend/tests/test_cache.py
Day 6: Tests for cache_service.py

Tests use mocked Redis (no real Upstash) via AsyncMock.
All tests verify:
  - key/field normalisation
  - cache miss / hit path
  - cache_hit flag set on retrieval
  - invalidation via scan_delete_pattern
  - list_user_qa_pairs
  - graceful degradation when Redis raises
"""
from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.query import LatencyBreakdown, QueryResponse, RouteType


# ── Helpers -------------------------------------------------------------------

def _make_response(**kwargs) -> QueryResponse:
    defaults = dict(
        answer="Test answer",
        sources=[],
        route_type=RouteType.TEXT,
        cache_hit=False,
        model_used="test-model",
        provider_used="groq",
        latency=LatencyBreakdown(),
        token_usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        cost_usd=0.001,
    )
    defaults.update(kwargs)
    return QueryResponse(**defaults)


def _norm_field(query: str) -> str:
    return hashlib.sha256(query.lower().strip().encode()).hexdigest()


# ── Key / field helpers -------------------------------------------------------

def test_cache_key_format():
    """Hash key follows user:{id}:qa:{doc_id} pattern."""
    from app.services.cache_service import _cache_key
    key = _cache_key("user-123", "doc-abc")
    assert key == "user:user-123:qa:doc-abc"


def test_cache_key_all_docs():
    """When no document filter, key uses __all__ sentinel."""
    from app.services.cache_service import _cache_key, _doc_key
    key = _cache_key("user-1", _doc_key(None))
    assert key == "user:user-1:qa:__all__"


def test_field_key_normalisation():
    """'Hello ' and 'hello' produce the same field key."""
    from app.services.cache_service import _field_key
    assert _field_key("Hello World") == _field_key("hello world")
    assert _field_key("  What is revenue?  ") == _field_key("what is revenue?")


def test_doc_key_none_returns_all():
    from app.services.cache_service import _doc_key
    assert _doc_key(None) == "__all__"
    assert _doc_key([]) == "__all__"


def test_doc_key_single_doc():
    from app.services.cache_service import _doc_key
    assert _doc_key(["doc-123"]) == "doc-123"


def test_doc_key_multi_docs_returns_all():
    from app.services.cache_service import _doc_key
    # Multiple docs -> __all__ sentinel
    assert _doc_key(["doc-1", "doc-2"]) == "__all__"


# ── Cache miss ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_miss_returns_none():
    """get_cached_response returns None when Redis returns None."""
    with patch("app.services.cache_service.redis_client") as mock_rc:
        mock_rc.hget = AsyncMock(return_value=None)
        from app.services import cache_service
        result = await cache_service.get_cached_response("u1", None, "test query")
    assert result is None


# ── Cache hit ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_returns_response():
    """get_cached_response returns a QueryResponse when Redis has the value."""
    stored = _make_response(answer="Cached answer")
    raw_json = stored.model_dump_json()

    with patch("app.services.cache_service.redis_client") as mock_rc:
        mock_rc.hget = AsyncMock(return_value=raw_json)
        from app.services import cache_service
        result = await cache_service.get_cached_response("u1", ["doc-1"], "my question")

    assert result is not None
    assert result.answer == "Cached answer"


@pytest.mark.asyncio
async def test_cache_hit_stamps_cache_hit_true():
    """Retrieved response always has cache_hit=True."""
    stored = _make_response(cache_hit=False)  # stored as False
    raw_json = stored.model_dump_json()

    with patch("app.services.cache_service.redis_client") as mock_rc:
        mock_rc.hget = AsyncMock(return_value=raw_json)
        from app.services import cache_service
        result = await cache_service.get_cached_response("u1", None, "anything")

    assert result.cache_hit is True


# ── Cache set ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_set_stores_response():
    """set_cached_response calls hset with correct key/field."""
    response = _make_response()

    mock_client = AsyncMock()
    mock_client.expire = AsyncMock()

    with patch("app.services.cache_service.redis_client") as mock_rc:
        mock_rc.hset = AsyncMock()
        mock_rc.get_redis = MagicMock(return_value=mock_client)

        from app.services import cache_service
        await cache_service.set_cached_response("u1", ["doc-1"], "my question", response)

        expected_key = "user:u1:qa:doc-1"
        expected_field = _norm_field("my question")
        mock_rc.hset.assert_called_once()
        call_args = mock_rc.hset.call_args[0]
        assert call_args[0] == expected_key
        assert call_args[1] == expected_field


@pytest.mark.asyncio
async def test_cache_set_stored_value_has_cache_hit_false():
    """The stored JSON always has cache_hit=False so reader can stamp True."""
    response = _make_response(cache_hit=True)
    stored_json = None

    async def capture_hset(key, field, value):
        nonlocal stored_json
        stored_json = value

    mock_client = AsyncMock()
    mock_client.expire = AsyncMock()

    with patch("app.services.cache_service.redis_client") as mock_rc:
        mock_rc.hset = capture_hset
        mock_rc.get_redis = MagicMock(return_value=mock_client)

        from app.services import cache_service
        await cache_service.set_cached_response("u1", None, "q", response)

    assert stored_json is not None
    stored_obj = QueryResponse.model_validate_json(stored_json)
    assert stored_obj.cache_hit is False


# ── Cache invalidation -------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_invalidation_calls_scan_delete():
    """invalidate_document_cache calls scan_delete_pattern with correct pattern."""
    with patch("app.services.cache_service.redis_client") as mock_rc:
        mock_rc.scan_delete_pattern = AsyncMock(return_value=3)
        from app.services import cache_service
        deleted = await cache_service.invalidate_document_cache("doc-abc")

    mock_rc.scan_delete_pattern.assert_called_once_with("*:qa:doc-abc")
    assert deleted == 3


# ── list_user_qa_pairs -------------------------------------------------------

@pytest.mark.asyncio
async def test_list_user_qa_pairs_returns_all_entries():
    """list_user_qa_pairs deserialises all hash fields into QueryResponse objects."""
    r1 = _make_response(answer="Answer 1")
    r2 = _make_response(answer="Answer 2")
    raw_pairs = {
        _norm_field("q1"): r1.model_dump_json(),
        _norm_field("q2"): r2.model_dump_json(),
    }

    with patch("app.services.cache_service.redis_client") as mock_rc:
        mock_rc.hgetall = AsyncMock(return_value=raw_pairs)
        from app.services import cache_service
        results = await cache_service.list_user_qa_pairs("u1", ["doc-1"])

    assert len(results) == 2
    answers = {r["response"].answer for r in results}
    assert "Answer 1" in answers
    assert "Answer 2" in answers


@pytest.mark.asyncio
async def test_list_user_qa_pairs_empty_when_no_cache():
    """Returns empty list when hash is empty."""
    with patch("app.services.cache_service.redis_client") as mock_rc:
        mock_rc.hgetall = AsyncMock(return_value={})
        from app.services import cache_service
        results = await cache_service.list_user_qa_pairs("u1", None)

    assert results == []


# ── Graceful degradation -----------------------------------------------------

@pytest.mark.asyncio
async def test_get_cached_response_degrades_gracefully():
    """If Redis raises, get_cached_response returns None (no crash)."""
    with patch("app.services.cache_service.redis_client") as mock_rc:
        mock_rc.hget = AsyncMock(side_effect=ConnectionError("Redis down"))
        from app.services import cache_service
        result = await cache_service.get_cached_response("u1", None, "q")

    assert result is None


@pytest.mark.asyncio
async def test_set_cached_response_degrades_gracefully():
    """If Redis raises, set_cached_response does not crash."""
    response = _make_response()
    with patch("app.services.cache_service.redis_client") as mock_rc:
        mock_rc.hset = AsyncMock(side_effect=ConnectionError("Redis down"))
        from app.services import cache_service
        # Should not raise
        await cache_service.set_cached_response("u1", None, "q", response)


@pytest.mark.asyncio
async def test_invalidate_document_cache_degrades_gracefully():
    """If Redis raises, invalidate_document_cache returns 0 (no crash)."""
    with patch("app.services.cache_service.redis_client") as mock_rc:
        mock_rc.scan_delete_pattern = AsyncMock(side_effect=ConnectionError("Redis down"))
        from app.services import cache_service
        deleted = await cache_service.invalidate_document_cache("doc-1")

    assert deleted == 0
