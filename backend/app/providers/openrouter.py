"""
backend/app/providers/openrouter.py
Shared OpenRouter HTTP client.
All NVIDIA model inference routes through this client.
Model → Provider mapping:
  nvidia/llama-nemotron-embed-vl-1b-v2   → OpenRouter
  nvidia/llama-nemotron-rerank-vl-1b-v2  → OpenRouter
  nvidia/nemotron-3-super-120b-a12b:free → OpenRouter
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class OpenRouterClient:
    """
    Shared async HTTP client for OpenRouter API.
    Provides auth headers and base URL for all NVIDIA model calls via OpenRouter.
    """

    BASE_URL = settings.OPENROUTER_BASE_URL

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=self._auth_headers(),
                timeout=httpx.Timeout(settings.TIMEOUT_SECONDS),
            )
        return self._client

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://multimodal-rag-app",
            "X-Title": "Multimodal RAG",
        }

    async def post(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        POST to an OpenRouter endpoint.
        Raises httpx.HTTPStatusError on non-2xx responses.
        """
        logger.debug("OpenRouter request", endpoint=endpoint, model=payload.get("model"))
        response = await self.client.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Module-level singleton — shared across all OpenRouter-based providers
openrouter_client = OpenRouterClient()
