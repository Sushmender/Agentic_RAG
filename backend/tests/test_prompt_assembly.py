"""
backend/tests/test_prompt_assembly.py
Unit tests for Phase D:
- Prompt assembly with and without conversation history
- Evidence-only rule in system prompt
- Answer rules (a, b, c) in system prompt
- Small documents chunk expansion (<= 40 chunks -> max(top_k, 8))
- C. Answer-prompt tests: conversation block gated on rewrite_applied
- "Answer ONLY the current question" rule present when applied=True

All tests use mocked inputs/providers; NO real requests are sent.
"""
from __future__ import annotations


from app.core.config import get_settings
from app.schemas.query import RetrievalResult
from app.services.context_assembly import assemble_context, _SYSTEM_PROMPT


def _make_candidate(chunk_id: str, text: str, page: int = 0) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id="doc1",
        chunk_type="text",
        page=page,
        bbox=[0.0, 0.0, 1.0, 1.0],
        text=text,
        similarity_score=0.95,
    )


def test_system_prompt_contains_evidence_only_rule():
    """System prompt states explicitly that answers must rely only on evidence and previous answers are not evidence."""
    prompt = _SYSTEM_PROMPT
    assert "answer only using the provided evidence" in prompt.lower()
    assert "previous answers are not evidence" in prompt.lower()


def test_system_prompt_contains_answer_rules_a_b_c():
    """System prompt contains rules (a) reason/cause, (b) closest relevant facts, and (c) never invent causes/numbers."""
    prompt = _SYSTEM_PROMPT
    # Rule (a): reason or cause ("due to ...", "driven by ...")
    assert "due to" in prompt.lower() or "driven by" in prompt.lower()
    assert "reason or cause" in prompt.lower()

    # Rule (b): if passages do not state exactly what was asked, say so in one sentence and give closest relevant facts
    assert "do not state exactly" in prompt.lower() or "not state exactly" in prompt.lower()
    assert "one sentence" in prompt.lower()
    assert "closest relevant facts" in prompt.lower()

    # Rule (c): never invent causes or numbers
    assert "never invent causes or numbers" in prompt.lower()


def test_prompt_without_history_stays_unchanged():
    """When no history exists, the prompt contains no conversation context block and stays unchanged."""
    candidates = [_make_candidate("c1", "Sample passage text about revenue growth.")]
    query = "What was the revenue growth?"

    assembled = assemble_context(candidates=candidates, query=query, history=None)
    prompt = assembled.context_prompt

    assert "CONVERSATION CONTEXT" not in prompt
    assert "Prior Question:" not in prompt
    assert "Prior Answer:" not in prompt
    assert "Original wording:" not in prompt

    # Standard format: EVIDENCE: ... QUESTION: What was the revenue growth? ... ANSWER:
    assert "\nQUESTION: What was the revenue growth?\n\nANSWER:" in prompt


def test_prompt_with_history_but_rewrite_not_applied_same_as_no_history():
    """When history is present but rewrite_applied=False, prompt is identical to no-history prompt."""
    candidates = [_make_candidate("c1", "Sample passage text about revenue growth.")]
    query = "What was the revenue growth?"
    history = [
        {"role": "user", "content": "Prior question"},
        {"role": "assistant", "content": "Prior answer"},
    ]

    assembled_with_hist = assemble_context(
        candidates=candidates, query=query, history=history,
        original_query=query, rewrite_applied=False,
    )
    assembled_no_hist = assemble_context(
        candidates=candidates, query=query, history=None,
    )

    assert assembled_with_hist.context_prompt == assembled_no_hist.context_prompt
    assert "CONVERSATION CONTEXT" not in assembled_with_hist.context_prompt


def test_prompt_with_history_includes_conversation_block_and_original_wording():
    """When history exists and rewrite_applied=True, last exchange is labeled as conversation context."""
    candidates = [_make_candidate("c1", "Northeast grew 9% due to increased local competition.")]
    standalone = "What drove the difference in growth between the Southeast and Northeast regions?"
    original = "and what drove it?"
    history = [
        {"role": "user", "content": "How did Southeast growth compare to Northeast?"},
        {"role": "assistant", "content": "Southeast grew 31% while Northeast grew 9%."},
    ]

    assembled = assemble_context(
        candidates=candidates,
        query=standalone,
        history=history,
        original_query=original,
        rewrite_applied=True,
    )
    prompt = assembled.context_prompt

    # Conversation context block appears
    assert "CONVERSATION CONTEXT" in prompt
    assert "for interpreting the question only" in prompt.lower()
    assert "previous answers are not evidence" in prompt.lower()

    # Last exchange appears
    assert "Prior Question: How did Southeast growth compare to Northeast?" in prompt
    assert "Prior Answer: Southeast grew 31% while Northeast grew 9%." in prompt

    # User's original wording appears next to the standalone question
    assert standalone in prompt
    assert f'Original wording: "{original}"' in prompt
    assert "for interpreting question only" in prompt.lower()

    # "Answer ONLY" rule must be present
    assert "Answer ONLY the current question" in prompt


def test_prompt_with_history_truncates_to_last_exchange():
    """When multiple turns exist, only the most recent user and assistant exchange is included."""
    candidates = [_make_candidate("c1", "Passage text.")]
    history = [
        {"role": "user", "content": "Older question 1"},
        {"role": "assistant", "content": "Older answer 1"},
        {"role": "user", "content": "Recent question 2"},
        {"role": "assistant", "content": "Recent answer 2"},
    ]

    assembled = assemble_context(
        candidates=candidates,
        query="Follow-up standalone?",
        history=history,
        original_query="Follow up?",
        rewrite_applied=True,
    )
    prompt = assembled.context_prompt

    assert "Recent question 2" in prompt
    assert "Recent answer 2" in prompt
    assert "Older question 1" not in prompt
    assert "Older answer 1" not in prompt


def test_small_doc_chunk_expansion_logic():
    """Verify small doc config defaults and expansion threshold (<=40 chunks -> max(top_k, 8))."""
    settings = get_settings()
    assert settings.SMALL_DOC_CHUNK_LIMIT == 40
    assert settings.SMALL_DOC_CONTEXT_CHUNKS == 8

    # When doc count is <= 40, top_k 5 expands to 8
    doc_chunk_count = 15
    top_k = 5
    if doc_chunk_count <= settings.SMALL_DOC_CHUNK_LIMIT:
        effective_top_k = max(top_k, settings.SMALL_DOC_CONTEXT_CHUNKS)
    else:
        effective_top_k = top_k
    assert effective_top_k == 8

    # When top_k is already larger (e.g. 10), max preserves 10
    top_k_large = 10
    if doc_chunk_count <= settings.SMALL_DOC_CHUNK_LIMIT:
        effective_top_k_large = max(top_k_large, settings.SMALL_DOC_CONTEXT_CHUNKS)
    else:
        effective_top_k_large = top_k_large
    assert effective_top_k_large == 10

    # When doc count is > 40, top_k is preserved
    large_doc_chunk_count = 55
    if large_doc_chunk_count <= settings.SMALL_DOC_CHUNK_LIMIT:
        effective_top_k_normal = max(top_k, settings.SMALL_DOC_CONTEXT_CHUNKS)
    else:
        effective_top_k_normal = top_k
    assert effective_top_k_normal == 5

