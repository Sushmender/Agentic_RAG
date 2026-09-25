"""
backend/app/providers/groq.py
Groq API client — Primary LLM (Qwen 3.8 27B).

Uses Groq's OpenAI-compatible /chat/completions endpoint.
Model: qwen/qwen3.8-27b (from settings.PRIMARY_LLM_MODEL)

Return shape (BaseLLMProvider contract):
  {
    "content":       str,    # generated text
    "model":         str,    # model name used
    "provider":      str,    # "groq"
    "input_tokens":  int,
    "output_tokens": int,
    "total_tokens":  int,
    "cost_usd":      float,  # estimated (Groq pricing)
    "latency_ms":    float,
  }

Cost estimation (as of 2025):
  Groq Qwen 3.8 27B: ~$0.29 / 1M input, ~$0.59 / 1M output
"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.retries import with_retry
from app.providers.base import BaseLLMProvider

logger = get_logger(__name__)
settings = get_settings()

# Groq Qwen 3.8 27B pricing (per token)
_GROQ_INPUT_COST_PER_TOKEN = 0.29 / 1_000_000
_GROQ_OUTPUT_COST_PER_TOKEN = 0.59 / 1_000_000


class GroqProvider(BaseLLMProvider):
    """
    Groq inference for Primary LLM (Qwen 3.8 27B).
    Used as the first-choice LLM. Fallback to OpenRouter Nemotron on any failure.
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=get_settings().GROQ_BASE_URL,
                headers={
                    "Authorization": f"Bearer {get_settings().GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(get_settings().TIMEOUT_SECONDS),
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
        Call Groq chat completions with Qwen 3.8 27B.

        Args:
            prompt:        User-facing prompt (assembled context + question).
            system_prompt: Optional system instruction (defaults to grounded-answer instruction).
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
            model=get_settings().PRIMARY_LLM_MODEL,
            provider="groq",
            max_tokens=max_tokens,
        )
        log.info("Calling Groq LLM")

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
            "Groq generation complete",
            input_tokens=result.get("input_tokens"),
            output_tokens=result.get("output_tokens"),
            cost_usd=result.get("cost_usd"),
            latency_ms=latency_ms,
        )
        return result

    @with_retry(
        max_attempts=3,
        wait_min=1.0,
        wait_max=10.0,
        retry_on=(httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError),
        provider_name="Groq",
    )
    async def _call_with_retry(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int,
        temperature: float,
        log_context: Any,
    ) -> dict[str, Any]:
        """Single Groq API call with retry decoration."""
        cfg = get_settings()
        model = cfg.PRIMARY_LLM_MODEL

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

        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        content: str = data["choices"][0]["message"]["content"]
        usage: dict = data.get("usage", {})
        input_tokens: int = usage.get("prompt_tokens", 0)
        output_tokens: int = usage.get("completion_tokens", 0)
        total_tokens: int = usage.get("total_tokens", input_tokens + output_tokens)

        cost_usd: float = round(
            input_tokens * _GROQ_INPUT_COST_PER_TOKEN
            + output_tokens * _GROQ_OUTPUT_COST_PER_TOKEN,
            6,
        )

        log_context.debug(
            "Groq raw response parsed",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return {
            "content": content,
            "model": model,
            "provider": "groq",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
            "latency_ms": 0.0,  # Overwritten by caller after wall-clock timing
        }

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Module-level singleton
groq_provider = GroqProvider()
