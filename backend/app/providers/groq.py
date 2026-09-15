"""
backend/app/providers/groq.py
Groq API client stub for primary LLM (Qwen 27B).
Full implementation on Day 5.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import BaseLLMProvider

logger = get_logger(__name__)
settings = get_settings()


class GroqProvider(BaseLLMProvider):
    """
    Groq inference for Primary LLM (Qwen 27B / qwen-qwq-32b).
    Used as the first-choice LLM. Fallback to OpenRouter Nemotron on failure.
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.GROQ_BASE_URL,
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(settings.TIMEOUT_SECONDS),
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """
        Call Groq chat completions with Qwen 27B.
        Returns structured dict with answer, tokens, cost, latency.
        Full implementation: Day 5.
        """
        # Stub — implemented Day 5
        raise NotImplementedError("GroqProvider.generate() — implemented Day 5")

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Module-level singleton
groq_provider = GroqProvider()
