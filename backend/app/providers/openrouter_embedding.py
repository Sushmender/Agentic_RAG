"""
backend/app/providers/openrouter_embedding.py
Stub for NVIDIA multimodal embedding via OpenRouter.
Model: nvidia/llama-nemotron-embed-vl-1b-v2
Provider: OpenRouter
Full implementation: Day 3.
"""
from __future__ import annotations

from typing import Any, List

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import BaseEmbeddingProvider
from app.providers.openrouter import openrouter_client

logger = get_logger(__name__)
settings = get_settings()


class OpenRouterEmbeddingProvider(BaseEmbeddingProvider):
    """
    OpenRouter embedding provider using nvidia/llama-nemotron-embed-vl-1b-v2.
    Supports passage mode (indexing) and query mode (retrieval).
    Full implementation: Day 3.
    """

    MODEL = settings.EMBEDDING_MODEL

    async def embed_passages(
        self,
        texts: List[str],
        batch_size: int = 16,
    ) -> List[List[float]]:
        """Embed document passages in passage mode. Full implementation: Day 3."""
        raise NotImplementedError("OpenRouterEmbeddingProvider — implemented Day 3")

    async def embed_query(self, text: str) -> List[float]:
        """Embed a user query in query mode. Full implementation: Day 3."""
        raise NotImplementedError("OpenRouterEmbeddingProvider — implemented Day 3")


# Module-level singleton
embedding_provider = OpenRouterEmbeddingProvider()
