"""
backend/app/providers/openrouter_reranker.py
Stub for NVIDIA multimodal reranker via OpenRouter.
Model: nvidia/llama-nemotron-rerank-vl-1b-v2
Provider: OpenRouter
Full implementation: Day 5.
"""
from __future__ import annotations

from typing import Any, List

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import BaseRerankerProvider

logger = get_logger(__name__)
settings = get_settings()


class OpenRouterRerankerProvider(BaseRerankerProvider):
    """
    OpenRouter reranker using nvidia/llama-nemotron-rerank-vl-1b-v2.
    Reranks Top-N retrieval candidates to Top-K final context.
    NEVER reranks full collection.
    Full implementation: Day 5.
    """

    MODEL = settings.RERANKER_MODEL

    async def rerank(
        self,
        query: str,
        candidates: List[dict[str, Any]],
        top_k: int = 5,
    ) -> List[dict[str, Any]]:
        """Rerank candidates. Full implementation: Day 5."""
        raise NotImplementedError("OpenRouterRerankerProvider — implemented Day 5")


# Module-level singleton
reranker_provider = OpenRouterRerankerProvider()
