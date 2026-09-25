"""
backend/app/providers/openrouter_reranker.py
NVIDIA multimodal reranker via OpenRouter.
Model: nvidia/llama-nemotron-rerank-vl-1b-v2:free

API shape (OpenRouter /rerank):
  POST /rerank
  {
    "model": "nvidia/llama-nemotron-rerank-vl-1b-v2:free",
    "query": "...",
    "documents": ["text1", "text2", ...]
  }
  Response: { "results": [{ "index": 0, "relevance_score": 0.95 }, ...] }

Design decisions:
  - Input candidates are passed as text strings; original dicts are mapped back by index.
  - top_k slicing is applied AFTER sorting by relevance_score descending.
  - Never reranks full collection — only retrieved Top-N candidates.
  - Retries on HTTP 429 / 5xx with exponential backoff via @with_retry.
  - Tracks latency per call for telemetry.
"""
from __future__ import annotations

import time
from typing import Any, List

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.retries import with_retry
from app.providers.base import BaseRerankerProvider
from app.providers.openrouter import openrouter_client

logger = get_logger(__name__)
settings = get_settings()

_ENDPOINT = "/rerank"


class OpenRouterRerankerProvider(BaseRerankerProvider):
    """
    OpenRouter reranker using nvidia/llama-nemotron-rerank-vl-1b-v2:free.
    Reranks Top-N retrieval candidates to Top-K final context chunks.
    NEVER reranks the full ChromaDB collection.
    """

    @property
    def model(self) -> str:
        return get_settings().RERANKER_MODEL

    async def rerank(
        self,
        query: str,
        candidates: List[dict[str, Any]],
        top_k: int = 5,
    ) -> List[dict[str, Any]]:
        """
        Rerank candidate chunks given a query using NVIDIA multimodal reranker.

        Args:
            query:      The user's original query string.
            candidates: List of candidate dicts (each must have 'text' and 'chunk_id').
            top_k:      Maximum number of top candidates to return after reranking.

        Returns:
            Top-K candidates sorted by relevance_score descending.
            Each dict has an added 'relevance_score' field (float 0–1).
        """
        if not candidates:
            return []

        # Clamp top_k to available candidates
        top_k = min(top_k, len(candidates))

        t0 = time.monotonic()
        log = logger.bind(
            model=self.model,
            query_preview=query[:80],
            candidates_count=len(candidates),
            top_k=top_k,
        )
        log.info("Calling OpenRouter reranker")

        try:
            reranked = await self._call_with_retry(
                query=query,
                candidates=candidates,
                log_context=log,
            )
        except Exception as exc:
            log.error("Reranker call failed", error=str(exc))
            raise

        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        log.info(
            "Reranking complete",
            latency_ms=latency_ms,
            returned=len(reranked),
        )

        # Slice to top_k after sorting
        reranked.sort(key=lambda x: x.get("relevance_score", 0.0), reverse=True)
        return reranked[:top_k]

    @with_retry(
        max_attempts=3,
        wait_min=1.0,
        wait_max=10.0,
        retry_on=(httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError),
        provider_name="OpenRouter/Reranker",
    )
    async def _call_with_retry(
        self,
        query: str,
        candidates: List[dict[str, Any]],
        log_context: Any,
    ) -> List[dict[str, Any]]:
        """
        Single rerank API call with retry decoration.
        Maps OpenRouter index-based results back to the original candidate dicts.
        """
        # Extract text strings for the API — preserve original order
        documents = [c.get("text", "") for c in candidates]

        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
        }

        response = await openrouter_client.post(_ENDPOINT, payload)

        # Map relevance scores back to candidate dicts by index
        results: List[dict[str, Any]] = response.get("results", [])

        reranked: List[dict[str, Any]] = []
        for item in results:
            idx = item.get("index", 0)
            score = float(item.get("relevance_score", 0.0))
            if 0 <= idx < len(candidates):
                enriched = dict(candidates[idx])  # shallow copy
                enriched["relevance_score"] = score
                reranked.append(enriched)

        log_context.debug(
            "Reranker raw response mapped",
            raw_results=len(results),
            mapped=len(reranked),
        )
        return reranked


# Module-level singleton
reranker_provider = OpenRouterRerankerProvider()
