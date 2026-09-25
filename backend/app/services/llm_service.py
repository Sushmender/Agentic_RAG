"""
backend/app/services/llm_service.py
LLM orchestration — primary (Groq) with automatic fallback (OpenRouter).

Flow:
  1. Try Groq (qwen/qwen3.8-27b) → fast inference, low cost
  2. On ANY exception → log reason → fallback to OpenRouter (Nemotron 120B :free)
  3. Return structured LLMResult with provider attribution

This service is the ONLY caller of GroqProvider and OpenRouterLLMProvider.
The query endpoint calls this service — never providers directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.logging import get_logger
from app.providers.groq import groq_provider
from app.providers.openrouter_llm import openrouter_llm_provider
from app.services.context_assembly import AssembledContext

logger = get_logger(__name__)


@dataclass
class LLMResult:
    """Structured result from LLM generation."""
    answer: str
    model_used: str
    provider_used: str        # "groq" | "openrouter"
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    fallback_triggered: bool = False
    fallback_reason: Optional[str] = None


async def generate_answer(
    assembled: AssembledContext,
    query: str,
    preferred_provider: str = "groq",
    max_tokens: int = 1024,
) -> LLMResult:
    """
    Generate a grounded answer using the primary LLM with automatic fallback.

    Args:
        assembled:          AssembledContext from context_assembly.assemble_context().
        query:              Original user query (already embedded in assembled.context_prompt).
        preferred_provider: "groq" (default) or "openrouter" (user-selected via frontend).
        max_tokens:         Maximum output tokens.

    Returns:
        LLMResult with answer, provenance, tokens, cost, and latency.
    """
    log = logger.bind(
        preferred_provider=preferred_provider,
        chunks_in_context=len(assembled.selected_chunks),
        tokens_est=assembled.total_tokens_est,
        query_preview=query[:80],
    )

    # ── Route by preferred provider ───────────────────────────────────────────
    if preferred_provider == "openrouter":
        # User explicitly chose OpenRouter — skip Groq entirely
        log.info("Using OpenRouter directly (user preference)")
        return await _call_openrouter(assembled, max_tokens, log, fallback=False)

    # ── Primary: Groq ─────────────────────────────────────────────────────────
    try:
        log.info("Calling primary LLM (Groq)")
        raw = await groq_provider.generate(
            prompt=assembled.context_prompt,
            system_prompt=assembled.system_prompt,
            max_tokens=max_tokens,
            temperature=0.0,
        )
        log.info(
            "Primary LLM succeeded",
            provider="groq",
            model=raw.get("model"),
            input_tokens=raw.get("input_tokens"),
            output_tokens=raw.get("output_tokens"),
            latency_ms=raw.get("latency_ms"),
        )
        return LLMResult(
            answer=raw["content"],
            model_used=raw["model"],
            provider_used="groq",
            input_tokens=raw.get("input_tokens", 0),
            output_tokens=raw.get("output_tokens", 0),
            total_tokens=raw.get("total_tokens", 0),
            cost_usd=raw.get("cost_usd", 0.0),
            latency_ms=raw.get("latency_ms", 0.0),
            fallback_triggered=False,
        )

    except Exception as groq_exc:
        # ── Fallback: OpenRouter ───────────────────────────────────────────────
        reason = f"{type(groq_exc).__name__}: {groq_exc}"
        log.warning(
            "Groq failed — triggering OpenRouter fallback",
            fallback_reason=reason,
        )
        return await _call_openrouter(
            assembled, max_tokens, log, fallback=True, fallback_reason=reason
        )


async def _call_openrouter(
    assembled: AssembledContext,
    max_tokens: int,
    log: object,
    fallback: bool,
    fallback_reason: Optional[str] = None,
) -> LLMResult:
    """Internal helper — calls OpenRouter Nemotron 120B."""
    raw = await openrouter_llm_provider.generate(
        prompt=assembled.context_prompt,
        system_prompt=assembled.system_prompt,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    log.info(  # type: ignore[attr-defined]
        "OpenRouter LLM succeeded",
        provider="openrouter",
        model=raw.get("model"),
        input_tokens=raw.get("input_tokens"),
        output_tokens=raw.get("output_tokens"),
        latency_ms=raw.get("latency_ms"),
        fallback=fallback,
    )
    return LLMResult(
        answer=raw["content"],
        model_used=raw["model"],
        provider_used="openrouter",
        input_tokens=raw.get("input_tokens", 0),
        output_tokens=raw.get("output_tokens", 0),
        total_tokens=raw.get("total_tokens", 0),
        cost_usd=raw.get("cost_usd", 0.0),
        latency_ms=raw.get("latency_ms", 0.0),
        fallback_triggered=fallback,
        fallback_reason=fallback_reason,
    )
