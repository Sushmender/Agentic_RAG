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

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.retries import with_retry
from app.providers.base import BaseEmbeddingProvider
from app.providers.openrouter import openrouter_client

logger = get_logger(__name__)
settings = get_settings()

_ENDPOINT = "/embeddings"


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
        Embed a single user query for retrieval.
        Uses input_type='query' — different representation than passage mode.

        Returns:
            Single embedding vector (1D list of floats).
        """
        results = await self._embed_batched(
            texts=[text],
            input_type="query",
            batch_size=1,
        )
        return results[0]

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

