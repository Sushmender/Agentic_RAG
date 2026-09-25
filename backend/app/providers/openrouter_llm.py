"""
backend/app/providers/openrouter_llm.py
OpenRouter fallback LLM — NVIDIA Nemotron 120B.
Model: nvidia/nemotron-3-super-120b-a12b:free

Uses the shared OpenRouterClient (same auth, same base URL as embeddings/reranker).
Activated automatically by llm_service.py when Groq fails or times out.

Return shape (BaseLLMProvider contract):
  {
    "content":       str,
    "model":         str,
    "provider":      str,   # "openrouter"
    "input_tokens":  int,
    "output_tokens": int,
    "total_tokens":  int,
    "cost_usd":      float,  # 0.0 for :free tier
    "latency_ms":    float,
  }
"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.retries import with_retry
from app.providers.base import BaseLLMProvider
from app.providers.openrouter import openrouter_client

logger = get_logger(__name__)

_ENDPOINT = "/chat/completions"


class OpenRouterLLMProvider(BaseLLMProvider):
    """
    OpenRouter LLM for fallback generation using nvidia/nemotron-3-super-120b-a12b:free.
    Activated by llm_service when Groq (primary) fails or times out.
    Same generate() interface as GroqProvider.
    """

    @property
    def model(self) -> str:
        return get_settings().FALLBACK_LLM_MODEL

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """
        Call OpenRouter chat completions with Nemotron 120B.

        Args:
            prompt:        User-facing prompt (assembled context + question).
            system_prompt: Optional system instruction.
            max_tokens:    Max output tokens.
            temperature:   Sampling temperature (0.0 = deterministic).

        Returns:
            dict conforming to BaseLLMProvider contract.
        """
        sys = system_prompt or (
            "You are a precise document assistant. "
            "Answer ONLY using the provided evidence. "
            "Cite sources with [Source N] notation. "
            "If the answer is not in the evidence, say so explicitly."
        )

        t0 = time.monotonic()
        log = logger.bind(
            model=self.model,
            provider="openrouter",
            max_tokens=max_tokens,
        )
        log.info("Calling OpenRouter fallback LLM (Nemotron 120B)")

        result = await self._call_with_retry(
            prompt=prompt,
            system_prompt=sys,
            max_tokens=max_tokens,
            temperature=temperature,
            log_context=log,
        )

        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        result["latency_ms"] = latency_ms

        log.info(
            "OpenRouter LLM generation complete",
            input_tokens=result.get("input_tokens"),
            output_tokens=result.get("output_tokens"),
            latency_ms=latency_ms,
        )
        return result

    @with_retry(
        max_attempts=3,
        wait_min=1.0,
        wait_max=10.0,
        retry_on=(httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError),
        provider_name="OpenRouter/LLM",
    )
    async def _call_with_retry(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int,
        temperature: float,
        log_context: Any,
    ) -> dict[str, Any]:
        """Single OpenRouter chat completions call with retry decoration."""
        model = self.model

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        data = await openrouter_client.post(_ENDPOINT, payload)

        content: str = data["choices"][0]["message"]["content"]
        usage: dict = data.get("usage", {})
        input_tokens: int = usage.get("prompt_tokens", 0)
        output_tokens: int = usage.get("completion_tokens", 0)
        total_tokens: int = usage.get("total_tokens", input_tokens + output_tokens)

        log_context.debug(
            "OpenRouter LLM raw response parsed",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return {
            "content": content,
            "model": model,
            "provider": "openrouter",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost_usd": 0.0,  # :free tier
            "latency_ms": 0.0,  # Overwritten by caller after wall-clock timing
        }


# Module-level singleton
openrouter_llm_provider = OpenRouterLLMProvider()
