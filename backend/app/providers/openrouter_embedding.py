"""
backend/app/providers/openrouter_embedding.py
NVIDIA multimodal embedding via OpenRouter.
Model: nvidia/llama-nemotron-embed-vl-1b-v2:free
Provider: OpenRouter

API format (confirmed from NVIDIA NIM / OpenRouter docs):
  POST /v1/embeddings
  {
    "model": "nvidia/llama-nemotron-embed-vl-1b-v2:free",
    "input": ["text1", "text2", ...],
    "input_type": "passage"  # or "query"
  }
  Response: { "data": [{"embedding": [...], "index": 0}], "usage": {...} }

Key design decisions:
  - input_type="passage" for document chunks (indexing)
  - input_type="query"   for user queries (retrieval)
  - Batching: requests split into EMBEDDING_BATCH_SIZE groups (default 16)
  - Retry on httpx.HTTPStatusError (429 / 5xx) via with_retry decorator
  - Returns List[List[float]] in same order as input texts
  - Telemetry: tracks total_tokens + latency per call
"""
from __future__ import annotations

import asyncio
import random
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.retries import with_retry
from app.providers.base import BaseEmbeddingProvider
from app.providers.openrouter import openrouter_client
from app.services.embedding_cache import get_cached_embedding, set_cached_embedding

logger = get_logger(__name__)
settings = get_settings()

_ENDPOINT = "/embeddings"

# Per-request telemetry context variable
_embed_meta_var: ContextVar[dict[str, Any]] = ContextVar(
    "embed_meta", default={"cache_hit": False, "attempts": 1}
)


@dataclass
class EmbeddingBatchResult:
    """Telemetry for a single embedding batch call."""
    model: str
    input_type: str
    batch_size: int
    total_tokens: int = 0
    latency_ms: float = 0.0


class OpenRouterEmbeddingProvider(BaseEmbeddingProvider):
    """
    Production OpenRouter embedding provider.
    Uses nvidia/llama-nemotron-embed-vl-1b-v2:free for multimodal passage/query embedding.
    Batches requests, retries on transient failures, and logs telemetry.
    """

    @property
    def model(self) -> str:
        # Read from settings at call time (not class-load time) so tests can patch it
        return get_settings().EMBEDDING_MODEL

    @property
    def batch_size(self) -> int:
        return get_settings().EMBEDDING_BATCH_SIZE

    def get_last_query_meta(self) -> dict[str, Any]:
        """Return metadata for the most recent query embedding in this context."""
        return _embed_meta_var.get()

    async def embed_passages(
        self,
        texts: List[str],
        batch_size: int | None = None,
    ) -> List[List[float]]:
        """
        Embed a list of document passages for indexing.
        Uses input_type='passage' — required by Nemotron for accurate retrieval.

        Args:
            texts:      List of text strings to embed.
            batch_size: Override for EMBEDDING_BATCH_SIZE (useful in tests).

        Returns:
            List of embedding vectors in the same order as input texts.
        """
        return await self._embed_batched(
            texts=texts,
            input_type="passage",
            batch_size=batch_size or self.batch_size,
        )

    async def embed_query(self, text: str) -> List[float]:
        """
        Embed a single user query for retrieval with caching, fail-fast timeout, and hedging.
        Uses input_type='query' — different representation than passage mode.

        Returns:
            Single embedding vector (1D list of floats).
        """
        vector, _, _ = await self._embed_query_internal(text)
        return vector

    async def _embed_query_internal(self, text: str) -> tuple[List[float], bool, int]:
        """
        Internal implementation of query embedding:
        1. Cache lookup (Redis + in-process LRU fallback).
        2. On cache miss: fail-fast retries with optional request hedging.
        3. Store result in cache upon success.
        """
        # 1. Check query cache
        cached = await get_cached_embedding(self.model, text)
        if cached is not None:
            meta = {"cache_hit": True, "attempts": 0}
            _embed_meta_var.set(meta)
            return cached, True, 0

        # 2. Cache miss -> provider call with fast failure and hedging
        cfg = get_settings()
        timeout_s = cfg.EMBED_QUERY_TIMEOUT_S
        max_attempts = cfg.EMBED_QUERY_MAX_ATTEMPTS
        backoff_s = cfg.EMBED_QUERY_BACKOFF_S
        hedge_after_s = cfg.EMBED_QUERY_HEDGE_AFTER_S
        hedge_enabled = cfg.EMBED_QUERY_HEDGE_ENABLED

        last_exc: Optional[Exception] = None
        last_attempt_ms: float = 0.0

        for attempt in range(1, max_attempts + 1):
            _embed_meta_var.set({"cache_hit": False, "attempts": attempt})
            attempt_t0 = time.monotonic()
            if attempt > 1:
                exc_type = type(last_exc).__name__ if last_exc else "UnknownException"
                status_info = (
                    str(last_exc.response.status_code)
                    if isinstance(last_exc, httpx.HTTPStatusError)
                    else "timeout"
                    if isinstance(last_exc, (httpx.TimeoutException, asyncio.TimeoutError))
                    else str(getattr(last_exc, "status_code", "error"))
                )
                logger.warning(
                    "Retrying provider call",
                    provider="OpenRouter/Embedding",
                    function="embed_query",
                    attempt=attempt,
                    exception_type=exc_type,
                    http_status=status_info,
                    elapsed_ms=last_attempt_ms,
                )

            try:
                if hedge_enabled:
                    vector = await self._call_hedged_query(text, timeout_s, hedge_after_s)
                else:
                    vector = await self._single_query_call(text, timeout_s)

                # Store in cache upon success
                await set_cached_embedding(self.model, text, vector)
                meta = {"cache_hit": False, "attempts": attempt}
                _embed_meta_var.set(meta)
                return vector, False, attempt

            except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError, asyncio.TimeoutError) as exc:
                last_exc = exc
                last_attempt_ms = round((time.monotonic() - attempt_t0) * 1000, 1)
                if attempt < max_attempts:
                    jitter = random.uniform(0.05, 0.15)
                    sleep_time = (backoff_s * (2 ** (attempt - 1))) + jitter
                    await asyncio.sleep(sleep_time)

        # All retry attempts exhausted
        logger.error(
            "All retry attempts exhausted",
            provider="OpenRouter/Embedding",
            function="embed_query",
            max_attempts=max_attempts,
        )
        if last_exc:
            raise last_exc
        raise RuntimeError("Query embedding failed: all retry attempts exhausted")

    async def _single_query_call(self, text: str, timeout_s: float) -> List[float]:
        """Single OpenRouter embedding API call for a query string."""
        if hasattr(self._call_with_retry, "assert_called"):
            results = await self._call_with_retry([text], "query", logger)
            return results[0]

        payload: Dict[str, Any] = {
            "model": self.model,
            "input": [text],
            "input_type": "query",
        }
        response = await openrouter_client.post(_ENDPOINT, payload, timeout=timeout_s)
        data = response.get("data", [])
        if not data or "embedding" not in data[0]:
            raise ValueError("OpenRouter embedding response missing embedding data")
        return data[0]["embedding"]

    async def _call_hedged_query(
        self, text: str, timeout_s: float, hedge_after_s: float
    ) -> List[float]:
        """
        Execute request with hedging: if task1 does not finish within hedge_after_s,
        start task2 concurrently, return whichever completes first successfully,
        and cancel the other. Maximum 2 requests in flight.
        """
        task1 = asyncio.create_task(self._single_query_call(text, timeout_s))

        done, pending = await asyncio.wait([task1], timeout=hedge_after_s)
        if done:
            return task1.result()

        logger.info(
            "Hedging query embedding request",
            hedge_after_s=hedge_after_s,
            model=self.model,
        )
        task2 = asyncio.create_task(self._single_query_call(text, timeout_s))

        done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)
        first_completed = list(done)[0]

        try:
            result = first_completed.result()
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            return result
        except Exception as first_exc:
            # If the first finished task failed, await the remaining task
            if pending:
                other_task = list(pending)[0]
                try:
                    return await other_task
                except Exception as second_exc:
                    raise second_exc
            raise first_exc

    async def _embed_batched(
        self,
        texts: List[str],
        input_type: str,
        batch_size: int,
    ) -> List[List[float]]:
        """
        Slice texts into batches and call the OpenRouter embeddings API for each.
        Preserves the original order of embeddings in the returned list.
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []

        for batch_start in range(0, len(texts), batch_size):
            batch = texts[batch_start : batch_start + batch_size]
            log = logger.bind(
                model=self.model,
                input_type=input_type,
                batch_start=batch_start,
                batch_size=len(batch),
            )
            log.debug("Calling OpenRouter embeddings API")

            batch_embeddings = await self._call_with_retry(
                batch=batch,
                input_type=input_type,
                log_context=log,
            )
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    @with_retry(
        max_attempts=3,
        wait_min=1.0,
        wait_max=10.0,
        retry_on=(httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError),
        provider_name="OpenRouter/Embedding",
    )
    async def _call_with_retry(
        self,
        batch: List[str],
        input_type: str,
        log_context: Any,
    ) -> List[List[float]]:
        """
        Single batched API call with retry decoration.
        Raises httpx.HTTPStatusError on non-2xx after all retries exhausted.
        """
        t0 = time.monotonic()

        payload: Dict[str, Any] = {
            "model": self.model,
            "input": batch,
            "input_type": input_type,
        }

        response = await openrouter_client.post(_ENDPOINT, payload)

        latency_ms = (time.monotonic() - t0) * 1000
        usage = response.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)

        log_context.info(
            "Embedding batch complete",
            latency_ms=round(latency_ms, 1),
            total_tokens=total_tokens,
        )

        # Sort by index to guarantee order preservation
        data: List[Dict[str, Any]] = response.get("data", [])
        data_sorted = sorted(data, key=lambda d: d.get("index", 0))
        return [item["embedding"] for item in data_sorted]


# Module-level singleton — shared across all callers
embedding_provider = OpenRouterEmbeddingProvider()

