"""
backend/tests/test_embed_optimization.py
Unit tests for query embedding optimizations:
  (a) Call that hangs once is retried within the new timeout
  (b) Hedging returns the faster of two calls
  (c) All attempts failing returns the existing error within bounded time
  (d) Cache hit skips the provider call
  (e) Redis outage falls back to in-process LRU cache
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import get_settings
from app.providers.openrouter_embedding import OpenRouterEmbeddingProvider
from app.services.embedding_cache import (
    get_cached_embedding,
    in_memory_lru,
    set_cached_embedding,
)


@pytest.fixture(autouse=True)
def clean_cache():
    """Ensure in-memory LRU is empty before and after each test."""
    in_memory_lru.clear()
    yield
    in_memory_lru.clear()


@pytest.mark.asyncio
async def test_call_hangs_once_retried_within_new_timeout(monkeypatch):
    """
    (a) A call that hangs once is retried within the new fast timeout (not 30s).
    First attempt raises TimeoutException; second attempt succeeds.
    """
    provider = OpenRouterEmbeddingProvider()
    settings = get_settings()

    monkeypatch.setattr(settings, "EMBED_QUERY_TIMEOUT_S", 0.1)
    monkeypatch.setattr(settings, "EMBED_QUERY_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "EMBED_QUERY_BACKOFF_S", 0.01)
    monkeypatch.setattr(settings, "EMBED_QUERY_HEDGE_ENABLED", False)

    dummy_vector = [0.42] * 2048
    call_count = 0

    async def mock_post(endpoint, payload, timeout=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ReadTimeout("Request timed out on attempt 1")
        return {"data": [{"embedding": dummy_vector, "index": 0}]}

    t0 = time.monotonic()
    with patch("app.providers.openrouter_embedding.openrouter_client.post", side_effect=mock_post):
        result = await provider.embed_query("query that hangs once")
    elapsed_ms = (time.monotonic() - t0) * 1000

    assert result == dummy_vector
    assert call_count == 2
    meta = provider.get_last_query_meta()
    assert meta["cache_hit"] is False
    assert meta["attempts"] == 2
    assert elapsed_ms < 1000  # Finishes in well under 1s, not 30s+


@pytest.mark.asyncio
async def test_hedging_returns_faster_of_two_calls(monkeypatch):
    """
    (b) Hedging starts a 2nd concurrent request after EMBED_QUERY_HEDGE_AFTER_S
    and returns whichever succeeds first, canceling the slower one.
    """
    provider = OpenRouterEmbeddingProvider()
    settings = get_settings()

    monkeypatch.setattr(settings, "EMBED_QUERY_TIMEOUT_S", 2.0)
    monkeypatch.setattr(settings, "EMBED_QUERY_HEDGE_AFTER_S", 0.05)
    monkeypatch.setattr(settings, "EMBED_QUERY_HEDGE_ENABLED", True)

    vector_slow = [0.1] * 2048
    vector_fast = [0.9] * 2048
    calls = []

    async def mock_post(endpoint, payload, timeout=None):
        call_index = len(calls) + 1
        calls.append(call_index)
        if call_index == 1:
            # First task: hangs / slow
            await asyncio.sleep(0.5)
            return {"data": [{"embedding": vector_slow, "index": 0}]}
        else:
            # Second task (hedged): fast response
            await asyncio.sleep(0.01)
            return {"data": [{"embedding": vector_fast, "index": 0}]}

    t0 = time.monotonic()
    with patch("app.providers.openrouter_embedding.openrouter_client.post", side_effect=mock_post):
        result = await provider.embed_query("hedging test query")
    elapsed_ms = (time.monotonic() - t0) * 1000

    assert result == vector_fast
    assert len(calls) == 2
    # Elapsed should be roughly hedge_after (50ms) + fast response (10ms) << 500ms
    assert elapsed_ms < 400


@pytest.mark.asyncio
async def test_all_attempts_failing_bounded_time(monkeypatch):
    """
    (c) All attempts failing returns existing error shape quickly
    within bounded time.
    """
    provider = OpenRouterEmbeddingProvider()
    settings = get_settings()

    monkeypatch.setattr(settings, "EMBED_QUERY_TIMEOUT_S", 0.05)
    monkeypatch.setattr(settings, "EMBED_QUERY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "EMBED_QUERY_BACKOFF_S", 0.02)
    monkeypatch.setattr(settings, "EMBED_QUERY_HEDGE_ENABLED", False)

    call_count = 0

    async def mock_post(endpoint, payload, timeout=None):
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("Simulated persistent timeout")

    t0 = time.monotonic()
    with patch("app.providers.openrouter_embedding.openrouter_client.post", side_effect=mock_post):
        with pytest.raises(httpx.ReadTimeout):
            await provider.embed_query("failing query")
    elapsed_ms = (time.monotonic() - t0) * 1000

    assert call_count == 3
    # 3 attempts with 0.05s timeout and small backoffs should finish in < 500ms
    assert elapsed_ms < 1000


@pytest.mark.asyncio
async def test_cache_hit_skips_provider_call():
    """
    (d) A cache hit skips the provider call and returns cached vector.
    """
    provider = OpenRouterEmbeddingProvider()
    dummy_vector = [0.77] * 2048
    post_mock = AsyncMock(return_value={"data": [{"embedding": dummy_vector, "index": 0}]})

    with patch("app.providers.openrouter_embedding.openrouter_client.post", post_mock):
        # 1st call: cache miss, calls provider
        res1 = await provider.embed_query("What is Multimodal RAG?")
        assert res1 == dummy_vector
        assert post_mock.call_count == 1
        meta1 = provider.get_last_query_meta()
        assert meta1["cache_hit"] is False
        assert meta1["attempts"] == 1

        # 2nd call (same query, different casing/whitespace): cache hit!
        res2 = await provider.embed_query("  what  is  multimodal rag? ")
        assert res2 == dummy_vector
        # Provider post must NOT be called again
        assert post_mock.call_count == 1
        meta2 = provider.get_last_query_meta()
        assert meta2["cache_hit"] is True
        assert meta2["attempts"] == 0


@pytest.mark.asyncio
async def test_redis_outage_falls_back_to_in_process_cache():
    """
    (e) When Redis is unavailable/outage, embedding cache seamlessly
    falls back to the in-process LRU cache without raising errors.
    """
    model = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    query = "test fallback under redis outage"
    vector = [0.123] * 2048

    # Simulate Redis being completely down
    with patch("app.services.embedding_cache.redis_client.get_redis", side_effect=RuntimeError("Redis connection refused")):
        # Set should not fail; writes to in-memory LRU
        await set_cached_embedding(model, query, vector)

        # Get should not fail; retrieves from in-memory LRU
        cached = await get_cached_embedding(model, query)
        assert cached == vector


@pytest.mark.asyncio
async def test_worst_case_query_embedding_time_bounded_at_12s(monkeypatch):
    """
    (f) Proves that with mocked hanging calls, the worst-case total query-embedding
    time is bounded at about 12 s (default settings: EMBED_QUERY_TIMEOUT_S=4.0,
    EMBED_QUERY_MAX_ATTEMPTS=2, EMBED_QUERY_HEDGE_AFTER_S=1.5, EMBED_QUERY_BACKOFF_S=0.5).
    """
    provider = OpenRouterEmbeddingProvider()
    settings = get_settings()

    monkeypatch.setattr(settings, "EMBED_QUERY_TIMEOUT_S", 4.0)
    monkeypatch.setattr(settings, "EMBED_QUERY_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "EMBED_QUERY_HEDGE_AFTER_S", 1.5)
    monkeypatch.setattr(settings, "EMBED_QUERY_BACKOFF_S", 0.5)
    monkeypatch.setattr(settings, "EMBED_QUERY_HEDGE_ENABLED", True)

    call_count = 0

    async def mock_hanging_post(endpoint, payload, timeout=None):
        nonlocal call_count
        call_count += 1
        to = timeout if timeout is not None else 4.0
        await asyncio.sleep(to)
        raise httpx.ReadTimeout(f"Mocked timeout after {to}s")

    t0 = time.monotonic()
    with patch("app.providers.openrouter_embedding.openrouter_client.post", side_effect=mock_hanging_post):
        with pytest.raises((httpx.ReadTimeout, RuntimeError)):
            await provider.embed_query("worst-case hanging query")
    elapsed_s = time.monotonic() - t0

    # Attempt 1: 4s task1 + 1.5s hedge + 4s task2 = 5.5s
    # Backoff: 0.5s + jitter (~0.1s) = ~0.6s
    # Attempt 2: 5.5s
    # Total elapsed is ~11.6s, strictly bounded around 12s.
    assert elapsed_s >= 11.0
    assert elapsed_s <= 12.5
    meta = provider.get_last_query_meta()
    assert meta["attempts"] == 2

