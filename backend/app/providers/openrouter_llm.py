"""
backend/app/providers/openrouter_llm.py
Stub for NVIDIA Nemotron 120B fallback LLM via OpenRouter.
Model: nvidia/nemotron-3-super-120b-a12b:free
Provider: OpenRouter
Full implementation: Day 5.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import BaseLLMProvider
from app.providers.openrouter import openrouter_client

logger = get_logger(__name__)
settings = get_settings()


class OpenRouterLLMProvider(BaseLLMProvider):
    """
    OpenRouter LLM for fallback generation using nvidia/nemotron-3-super-120b-a12b:free.
    Used when Groq (primary) fails or times out.
    Full implementation: Day 5.
    """

    MODEL = settings.FALLBACK_LLM_MODEL

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Generate via OpenRouter Nemotron. Full implementation: Day 5."""
        raise NotImplementedError("OpenRouterLLMProvider — implemented Day 5")


# Module-level singleton
openrouter_llm_provider = OpenRouterLLMProvider()
