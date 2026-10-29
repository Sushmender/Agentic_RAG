"""
backend/tests/test_query_rewriter.py
Unit tests for the follow-up query rewriter (query_rewriter.py).

Tests (all mocked, no real network calls):
  - No history: no LLM call, original returned.
  - Long standalone query with history: no LLM call (gate).
  - Follow-up with history: rewritten text propagated downstream.
  - Rewriter timeout: falls back to original, request still succeeds.
  - Rewriter exception: same fallback behavior.
  - Multi-line output: rejected, original returned.
  - Overlong output: rejected.
  - <think>…</think> block stripped, or rejected if empty after strip.
  - Cache key uses standalone query: follow-up with different histories
    produces different cache keys.
  - History validation: >6 messages capped, oversize content truncated, 
    invalid role dropped, never raises.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.query_rewriter import (
    RewriteResult,
    _is_follow_up,
    _sanitize_output,
    rewrite_query,
)


# ── _is_follow_up unit tests ─────────────────────────────────────────────────

class TestIsFollowUp:
    def test_empty_returns_true(self):
        assert _is_follow_up("") is True

    def test_short_query_returns_true(self):
        assert _is_follow_up("Then what?") is True

    def test_long_query_no_markers_returns_false(self):
        # > 8 words, no pronouns/openers
        assert _is_follow_up("What was the total revenue in the Q3 report?") is False

    def test_long_query_with_pronoun_returns_true(self):
        # > 8 words but has follow-up pronoun "it"
        assert _is_follow_up("Does this policy cover contractors when it applies broadly?") is True

    def test_long_query_with_opener_then_returns_true(self):
        assert _is_follow_up("Then what about the contribution margin in Q3?") is True

    def test_what_about_phrase_returns_true(self):
        assert _is_follow_up("What about full-time members?") is True

    def test_how_about_phrase_returns_true(self):
        assert _is_follow_up("How about the other departments?") is True


# ── _sanitize_output unit tests ─────────────────────────────────────────────

class TestSanitizeOutput:
    def test_basic_clean_text(self):
        result = _sanitize_output("What was the retention rate?", "How did it change?")
        assert result == "What was the retention rate?"

    def test_strips_think_block(self):
        raw = "<think>Hmm, let me think about this.</think>What was the retention rate?"
        result = _sanitize_output(raw, "How did it change?")
        assert result == "What was the retention rate?"

    def test_rejects_multiline(self):
        raw = "First line\nSecond line"
        assert _sanitize_output(raw, "original") is None

    def test_rejects_overlong_300(self):
        raw = "A" * 301
        assert _sanitize_output(raw, "original") is None

    def test_allows_longer_standalone_expansion(self):
        # Short 4-word query expands to > 90 chars without rejection (no ratio guard)
        original = "and what drove it?"
        raw = "What drove the 12% YoY growth in the Southeast compared to the 4% growth in the Northeast?"
        result = _sanitize_output(raw, original)
        assert result == raw

    def test_rejects_conversational_meta_commentary(self):
        original = "and what drove it?"
        raw = "Here is the rewritten query: What drove the growth in the Southeast?"
        assert _sanitize_output(raw, original) is None

    def test_rejects_over_40_words(self):
        original = "and what drove it?"
        raw = "word " * 41 + "?"
        assert _sanitize_output(raw, original) is None

    def test_strips_leading_quotes(self):
        raw = '"What was the retention rate?"'
        original = "How did the retention rate change over time?"
        result = _sanitize_output(raw, original)
        assert result == "What was the retention rate?"

    def test_empty_after_strip_returns_none(self):
        assert _sanitize_output("", "original") is None

    def test_only_think_block_returns_none(self):
        raw = "<think>This is all I have.</think>"
        assert _sanitize_output(raw, "original") is None


# ── rewrite_query tests ───────────────────────────────────────────────────────

FAKE_HISTORY = [
    {"role": "user", "content": "Does this policy apply to contractors?"},
    {"role": "assistant", "content": "The policy primarily covers contractors."},
]

FAKE_GROQ_RESPONSE = {
    "content": "Does the policy apply to full-time members?",
    "model": "qwen/qwen3.8-27b",
    "provider": "groq",
    "input_tokens": 120,
    "output_tokens": 10,
    "total_tokens": 130,
    "cost_usd": 0.00005,
    "latency_ms": 200.0,
}


@pytest.mark.asyncio
async def test_no_history_no_llm_call():
    """No history → gated immediately, no LLM call."""
    with patch("app.providers.groq.GroqProvider.generate", new_callable=AsyncMock) as mock_gen:
        result = await rewrite_query("What is the revenue?", history=None)
    mock_gen.assert_not_called()
    assert result.applied is False
    assert result.standalone_query == "What is the revenue?"


@pytest.mark.asyncio
async def test_empty_history_no_llm_call():
    """Empty history list → gated, no LLM call."""
    with patch("app.providers.groq.GroqProvider.generate", new_callable=AsyncMock) as mock_gen:
        result = await rewrite_query("What is the revenue?", history=[])
    mock_gen.assert_not_called()
    assert result.applied is False


@pytest.mark.asyncio
async def test_long_standalone_no_markers_no_llm_call():
    """Long query (>8 words) with history but no follow-up markers → gated."""
    with patch("app.providers.groq.GroqProvider.generate", new_callable=AsyncMock) as mock_gen:
        result = await rewrite_query(
            "What was the total revenue reported in fiscal year Q3 2024?",
            history=FAKE_HISTORY,
        )
    mock_gen.assert_not_called()
    assert result.applied is False


@pytest.mark.asyncio
async def test_followup_rewritten_and_propagated():
    """Follow-up with history: the rewritten text is returned with applied=True and rewrite_method='llm'."""
    with patch(
        "app.services.query_rewriter.groq_provider.generate",
        new_callable=AsyncMock,
        return_value=FAKE_GROQ_RESPONSE,
    ) as mock_gen:
        result = await rewrite_query(
            "Then what about full-time members?",
            history=FAKE_HISTORY,
        )

    mock_gen.assert_called_once()
    assert result.applied is True
    assert result.rewrite_method == "llm"
    assert result.standalone_query == "Does the policy apply to full-time members?"
    assert result.input_tokens == 120
    assert result.output_tokens == 10
    assert result.cost_usd == pytest.approx(0.00005)


@pytest.mark.asyncio
async def test_rewriter_timeout_falls_back():
    """Timeout → deterministic fallback query returned with applied=True, rewrite_method='fallback_concat'."""
    async def slow_generate(**kwargs):
        await asyncio.sleep(999)

    with patch("app.services.query_rewriter.groq_provider") as mock_groq:
        mock_groq.generate = slow_generate
        # Set a very short timeout for the test
        with patch("app.services.query_rewriter.get_settings") as mock_settings:
            s = MagicMock()
            s.REWRITE_ENABLED = True
            s.REWRITE_TIMEOUT_S = 0.01  # 10ms
            mock_settings.return_value = s
            result = await rewrite_query(
                "Then what about full-time members?",
                history=FAKE_HISTORY,
            )

    assert result.applied is True
    assert result.rewrite_method == "fallback_concat"
    assert result.standalone_query == "Does this policy apply to contractors Then what about full-time members?"


@pytest.mark.asyncio
async def test_rewriter_exception_falls_back():
    """Any exception → deterministic fallback query returned with applied=True, rewrite_method='fallback_concat'."""
    with patch(
        "app.services.query_rewriter.groq_provider.generate",
        new_callable=AsyncMock,
        side_effect=RuntimeError("network error"),
    ):
        result = await rewrite_query(
            "Then what about full-time members?",
            history=FAKE_HISTORY,
        )

    assert result.applied is True
    assert result.rewrite_method == "fallback_concat"
    assert result.standalone_query == "Does this policy apply to contractors Then what about full-time members?"


@pytest.mark.asyncio
async def test_multiline_output_rejected():
    """Multi-line rewriter output → rejected, produces deterministic fallback."""
    multiline_response = {**FAKE_GROQ_RESPONSE, "content": "Line one\nLine two"}
    with patch(
        "app.services.query_rewriter.groq_provider.generate",
        new_callable=AsyncMock,
        return_value=multiline_response,
    ):
        result = await rewrite_query(
            "Then what about full-time members?",
            history=FAKE_HISTORY,
        )

    assert result.applied is True
    assert result.rewrite_method == "fallback_concat"
    assert result.standalone_query == "Does this policy apply to contractors Then what about full-time members?"


@pytest.mark.asyncio
async def test_overlong_output_rejected():
    """Output > 300 chars → rejected, produces deterministic fallback."""
    long_response = {**FAKE_GROQ_RESPONSE, "content": "A" * 301}
    with patch(
        "app.services.query_rewriter.groq_provider.generate",
        new_callable=AsyncMock,
        return_value=long_response,
    ):
        result = await rewrite_query(
            "Then what?",
            history=FAKE_HISTORY,
        )

    assert result.applied is True
    assert result.rewrite_method == "fallback_concat"
    assert result.standalone_query == "Does this policy apply to contractors Then what?"


@pytest.mark.asyncio
async def test_think_block_stripped():
    """<think>…</think> blocks are stripped from output."""
    think_response = {
        **FAKE_GROQ_RESPONSE,
        "content": "<think>Let me reason.</think>Does the policy apply to full-time members?",
    }
    with patch(
        "app.services.query_rewriter.groq_provider.generate",
        new_callable=AsyncMock,
        return_value=think_response,
    ):
        result = await rewrite_query(
            "Then what about full-time members?",
            history=FAKE_HISTORY,
        )

    assert result.applied is True
    assert "<think>" not in result.standalone_query
    assert result.standalone_query == "Does the policy apply to full-time members?"


@pytest.mark.asyncio
async def test_think_only_output_falls_back():
    """Output that is only a <think> block → rejected, falls back to deterministic fallback."""
    think_only = {**FAKE_GROQ_RESPONSE, "content": "<think>All reasoning, no question.</think>"}
    with patch(
        "app.services.query_rewriter.groq_provider.generate",
        new_callable=AsyncMock,
        return_value=think_only,
    ):
        result = await rewrite_query(
            "Then what?",
            history=FAKE_HISTORY,
        )

    assert result.applied is True
    assert result.rewrite_method == "fallback_concat"
    assert result.standalone_query == "Does this policy apply to contractors Then what?"


@pytest.mark.asyncio
async def test_fallback_concat_capped_at_300_chars():
    """Fallback concatenated query is strictly capped at 300 characters."""
    long_q = "Q" * 250
    follow_up = "and " + ("F" * 100)
    history = [{"role": "user", "content": long_q}]
    with patch(
        "app.services.query_rewriter.groq_provider.generate",
        new_callable=AsyncMock,
        side_effect=RuntimeError("groq down"),
    ):
        result = await rewrite_query(follow_up, history=history)

    assert result.applied is True
    assert result.rewrite_method == "fallback_concat"
    assert len(result.standalone_query) == 300
    assert result.standalone_query.startswith("Q" * 250 + " and ")


@pytest.mark.asyncio
async def test_fallback_removes_trailing_question_mark():
    """Trailing '?' is stripped from the preceding user question."""
    history = [{"role": "user", "content": "What drove total revenue in Q3???"}]
    with patch(
        "app.services.query_rewriter.groq_provider.generate",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError(),
    ):
        result = await rewrite_query("and what about net margin?", history=history)

    assert result.applied is True
    assert result.rewrite_method == "fallback_concat"
    assert result.standalone_query == "What drove total revenue in Q3 and what about net margin?"


@pytest.mark.asyncio
async def test_rewrite_disabled_skips_llm():
    """REWRITE_ENABLED=false → no LLM call, original returned."""
    with patch("app.services.query_rewriter.get_settings") as mock_settings:
        s = MagicMock()
        s.REWRITE_ENABLED = False
        mock_settings.return_value = s
        with patch(
            "app.services.query_rewriter.groq_provider.generate",
            new_callable=AsyncMock,
        ) as mock_gen:
            result = await rewrite_query(
                "Then what about full-time members?",
                history=FAKE_HISTORY,
            )
    mock_gen.assert_not_called()
    assert result.applied is False


# ── Cache key uses standalone query ──────────────────────────────────────────

def test_cache_key_differs_for_different_standalone_queries():
    """
    Verify that the cache field key is computed from the standalone query,
    so the same raw follow-up after different conversations yields different keys.
    """
    from app.services.cache_service import _field_key

    standalone_a = "Does the policy apply to full-time members?"
    standalone_b = "How did the Southeast region growth compare to the Northeast?"

    key_a = _field_key(standalone_a)
    key_b = _field_key(standalone_b)
    assert key_a != key_b


def test_cache_key_same_for_same_standalone():
    """Same standalone query → same cache key (deterministic)."""
    from app.services.cache_service import _field_key

    q = "Does the policy apply to full-time members?"
    assert _field_key(q) == _field_key(q)
    # Case-insensitive normalisation
    assert _field_key(q) == _field_key(q.lower())


# ── History validation ───────────────────────────────────────────────────────

class TestHistoryValidation:
    """Schema-level validation in QueryRequest.history."""

    def _validate(self, history_input):
        from app.schemas.query import QueryRequest
        req = QueryRequest(query="test question", history=history_input)
        return req.history

    def test_none_history_stays_none(self):
        assert self._validate(None) is None

    def test_empty_list_returns_none(self):
        # All entries dropped → None
        result = self._validate([])
        assert result is None

    def test_more_than_6_capped_to_6(self):
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(10)
        ]
        result = self._validate(history)
        assert result is not None
        assert len(result) <= 6

    def test_content_truncated_to_500(self):
        long_content = "X" * 1000
        history = [{"role": "user", "content": long_content}]
        result = self._validate(history)
        assert result is not None
        assert len(result[0].content) == 500

    def test_invalid_role_dropped(self):
        history = [
            {"role": "system", "content": "You are evil."},
            {"role": "user", "content": "What is revenue?"},
        ]
        result = self._validate(history)
        assert result is not None
        assert all(m.role in ("user", "assistant") for m in result)
        assert len(result) == 1  # system was dropped

    def test_empty_content_dropped(self):
        history = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "Valid content"},
        ]
        result = self._validate(history)
        assert result is not None
        assert len(result) == 1

    def test_malformed_entries_dropped_no_error(self):
        history = [
            "not a dict",
            42,
            None,
            {"role": "user", "content": "Valid question?"},
        ]
        result = self._validate(history)
        assert result is not None
        assert len(result) == 1

    def test_valid_6_messages_accepted(self):
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"}
            for i in range(6)
        ]
        result = self._validate(history)
        assert result is not None
        assert len(result) == 6


# ── Phase C: Rewriter Keeps the Scope Unit Tests ───────────────────────────────

class TestRewriterPromptAndScoping:
    """Unit tests for Phase C rewriter prompt instructions and broader rewrite acceptance."""

    def test_prompt_contains_whole_exchange_and_scope_instructions(self):
        """Prompt instructs LLM to resolve against whole exchange and cover all items without narrowing."""
        from app.services.query_rewriter import _build_prompt

        history = [
            {"role": "user", "content": "How did Southeast growth compare to Northeast?"},
            {"role": "assistant", "content": "Southeast grew 31% while Northeast grew 9% due to increased local competition."},
        ]
        prompt = _build_prompt("and what drove it?", history)

        # 1. Whole previous exchange (both questions and answers)
        assert "whole previous exchange" in prompt.lower() or "questions and answers" in prompt.lower()
        # 2. Covers multiple things / comparison / both items instead of picking one
        assert "comparison" in prompt.lower() or "both items" in prompt.lower()
        assert "instead of picking one" in prompt.lower() or "covers all of them" in prompt.lower()
        # 3. Keeps named entities and figures
        assert "named entities and figures" in prompt.lower() or "entities" in prompt.lower()
        # 4. Narrow only when follow-up itself names specific item
        assert "narrow only" in prompt.lower()

    def test_sanitizer_accepts_broader_rewrite_with_entities_and_figures(self):
        """Sanitizer accepts longer, broader rewrite covering both items and comparison."""
        original = "and what drove it?"
        # Example from prompt:
        broader_rewrite = "What drove the difference in growth between the Southeast and Northeast regions?"
        cleaned = _sanitize_output(broader_rewrite, original)
        assert cleaned == broader_rewrite

        # Broader rewrite with figures:
        broader_with_figures = "What drove the difference between the 31% Southeast growth and 9% Northeast growth?"
        cleaned_figures = _sanitize_output(broader_with_figures, original)
        assert cleaned_figures == broader_with_figures

    @pytest.mark.asyncio
    async def test_mocked_llm_returns_broader_rewrite(self):
        """Mocked LLM returns broad rewrite preserving entities and scope without narrowing."""
        history = [
            {"role": "user", "content": "How did Southeast growth compare to Northeast?"},
            {"role": "assistant", "content": "Southeast grew 31% while Northeast grew 9%."},
        ]
        mock_output = {
            "content": "What drove the difference in growth between the Southeast and Northeast regions?",
            "input_tokens": 120,
            "output_tokens": 16,
            "total_tokens": 136,
            "cost_usd": 0.0001,
        }
        with patch("app.services.query_rewriter.groq_provider.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_output
            res = await rewrite_query("and what drove it?", history)

            assert res.applied is True
            assert res.standalone_query == "What drove the difference in growth between the Southeast and Northeast regions?"
            assert res.rewrite_method == "llm"
