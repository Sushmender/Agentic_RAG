"""
backend/tests/test_retrieval.py
Day 4 — Query Router + Retrieval Service tests (all mocked, no real API calls).

Tests:
  1.  test_route_text                    — plain question → RouteType.TEXT
  2.  test_route_multimodal              — "Show me the table" → MULTIMODAL
  3.  test_route_hybrid_connective       — keyword + "and" → HYBRID
  4.  test_route_hybrid_long_query       — keyword + long query → HYBRID
  5.  test_route_case_insensitive        — "SHOW THE TABLE" → MULTIMODAL
  6.  test_route_multiple_keywords       — multiple hits still routes correctly
  7.  test_retrieve_text_calls_chroma    — retrieve_text() calls query_similar, no filter
  8.  test_retrieve_multimodal_no_filter — retrieve_multimodal() passes no chunk_type filter
  9.  test_retrieve_hybrid_two_queries   — retrieve_hybrid() calls query_similar twice
  10. test_retrieve_hybrid_deduplicates  — overlapping chunk_ids deduplicated
  11. test_retrieve_hybrid_sorted        — merged results sorted by similarity_score desc
  12. test_document_ids_single_filter    — single doc_id → $eq filter applied
  13. test_document_ids_multi_filter     — multiple doc_ids → $in filter applied
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.query import RouteType
from app.services.query_router import route_query
from app.services import retrieval_service


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_raw_result(
    chunk_id: str,
    chunk_type: str = "text",
    similarity_score: float = 0.9,
    document_id: str = "doc1",
) -> Dict[str, Any]:
    """Build a raw ChromaDB result dict as returned by query_similar()."""
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "chunk_type": chunk_type,
        "page": 0,
        "bbox": [0.0, 0.0, 1.0, 1.0],
        "text": f"Sample text for {chunk_id}",
        "source": "test.pdf",
        "parser_version": "dpt-2-test",
        "similarity_score": similarity_score,
    }


FAKE_EMBEDDING: List[float] = [0.1] * 8


# ── Router tests (1–6) ────────────────────────────────────────────────────────

def test_route_text():
    """Plain factual question with no visual keywords → TEXT."""
    assert route_query("What is the total revenue?") == RouteType.TEXT


def test_route_text_general():
    """Another plain question → TEXT."""
    assert route_query("Summarize the key findings of the report.") == RouteType.TEXT


def test_route_multimodal():
    """Query referencing a table → MULTIMODAL (short query, no connective)."""
    assert route_query("Show me the table") == RouteType.MULTIMODAL


def test_route_multimodal_figure():
    """Query referencing a figure → MULTIMODAL."""
    assert route_query("What does the figure show?") == RouteType.MULTIMODAL


def test_route_hybrid_connective():
    """Visual keyword + connective 'and' → HYBRID."""
    assert route_query("Describe the chart and its text caption") == RouteType.HYBRID


def test_route_hybrid_long_query():
    """Visual keyword in a long compound query → HYBRID."""
    long_q = "What revenue numbers appear in the table for each quarter of the year"
    assert route_query(long_q) == RouteType.HYBRID


def test_route_case_insensitive():
    """All-caps visual keyword → MULTIMODAL (case-insensitive)."""
    assert route_query("SHOW THE TABLE") == RouteType.MULTIMODAL


def test_route_multiple_keywords():
    """Multiple visual keywords but short query → MULTIMODAL."""
    assert route_query("Show chart and graph") == RouteType.HYBRID  # "and" → hybrid


# ── Retrieval tests (7–13) ────────────────────────────────────────────────────

def test_retrieve_text_calls_chroma():
    """
    retrieve_text() should call query_similar once with no chunk_type where-filter.
    The where argument may be None (no document scope) or contain only a doc filter.
    """
    raw = [_fake_raw_result("c1")]
    with patch("app.services.retrieval_service.query_similar", return_value=raw) as mock_qs:
        results = retrieval_service.retrieve_text(
            query_embedding=FAKE_EMBEDDING,
            document_ids=None,
            top_n=5,
        )

    mock_qs.assert_called_once()
    call_kwargs = mock_qs.call_args
    # No chunk_type restriction should be in the where argument
    where_arg = call_kwargs.kwargs.get("where") or (call_kwargs.args[2] if len(call_kwargs.args) > 2 else None)
    if where_arg is not None:
        assert "chunk_type" not in str(where_arg), "retrieve_text must NOT filter by chunk_type"

    assert len(results) == 1
    assert results[0].chunk_id == "c1"


def test_retrieve_multimodal_no_filter():
    """
    retrieve_multimodal() should call query_similar once with no chunk_type filter.
    """
    raw = [_fake_raw_result("c2", chunk_type="table")]
    with patch("app.services.retrieval_service.query_similar", return_value=raw) as mock_qs:
        results = retrieval_service.retrieve_multimodal(
            query_embedding=FAKE_EMBEDDING,
            document_ids=None,
            top_n=5,
        )

    mock_qs.assert_called_once()
    call_kwargs = mock_qs.call_args
    where_arg = call_kwargs.kwargs.get("where") or (call_kwargs.args[2] if len(call_kwargs.args) > 2 else None)
    if where_arg is not None:
        assert "chunk_type" not in str(where_arg), "retrieve_multimodal must NOT filter by chunk_type"

    assert len(results) == 1
    assert results[0].chunk_type == "table"


def test_retrieve_hybrid_two_queries():
    """
    retrieve_hybrid() must call query_similar TWICE — once for text, once for visual.
    """
    text_raw = [_fake_raw_result("c_text", chunk_type="text", similarity_score=0.9)]
    visual_raw = [_fake_raw_result("c_vis", chunk_type="table", similarity_score=0.85)]

    call_order = []

    def side_effect(embedding, n_results, where):
        call_order.append(where)
        if where and "text" in str(where):
            return text_raw
        return visual_raw

    with patch("app.services.retrieval_service.query_similar", side_effect=side_effect) as mock_qs:
        results = retrieval_service.retrieve_hybrid(
            query_embedding=FAKE_EMBEDDING,
            document_ids=None,
            top_n=10,
        )

    assert mock_qs.call_count == 2, f"Expected 2 calls, got {mock_qs.call_count}"
    chunk_ids = {r.chunk_id for r in results}
    assert "c_text" in chunk_ids
    assert "c_vis" in chunk_ids


def test_retrieve_hybrid_deduplicates():
    """
    If the same chunk_id appears in both text and visual results, it should
    appear only once in the merged output.
    """
    shared = _fake_raw_result("shared_chunk", chunk_type="text", similarity_score=0.95)

    def side_effect(embedding, n_results, where):
        return [shared]

    with patch("app.services.retrieval_service.query_similar", side_effect=side_effect):
        results = retrieval_service.retrieve_hybrid(
            query_embedding=FAKE_EMBEDDING,
            document_ids=None,
            top_n=10,
        )

    ids = [r.chunk_id for r in results]
    assert ids.count("shared_chunk") == 1, "Duplicate chunk_id should appear only once"


def test_retrieve_hybrid_sorted():
    """
    Merged hybrid results must be sorted by similarity_score descending.
    """
    text_raw = [
        _fake_raw_result("low", chunk_type="text", similarity_score=0.5),
        _fake_raw_result("high", chunk_type="text", similarity_score=0.95),
    ]
    visual_raw = [
        _fake_raw_result("mid", chunk_type="table", similarity_score=0.75),
    ]

    def side_effect(embedding, n_results, where):
        if where and "text" in str(where):
            return text_raw
        return visual_raw

    with patch("app.services.retrieval_service.query_similar", side_effect=side_effect):
        results = retrieval_service.retrieve_hybrid(
            query_embedding=FAKE_EMBEDDING,
            document_ids=None,
            top_n=10,
        )

    scores = [r.similarity_score for r in results]
    assert scores == sorted(scores, reverse=True), "Results not sorted by similarity_score desc"


def test_document_ids_single_filter():
    """
    When a single document_id is provided, a $eq filter must be passed to query_similar.
    """
    with patch("app.services.retrieval_service.query_similar", return_value=[]) as mock_qs:
        retrieval_service.retrieve_text(
            query_embedding=FAKE_EMBEDDING,
            document_ids=["doc_abc"],
            top_n=5,
        )

    call_kwargs = mock_qs.call_args
    where_arg = call_kwargs.kwargs.get("where")
    assert where_arg is not None, "A where filter should be applied when document_ids is given"
    assert "doc_abc" in str(where_arg), "doc_abc should appear in the where filter"


def test_document_ids_multi_filter():
    """
    When multiple document_ids provided, a $in filter must be passed to query_similar.
    """
    with patch("app.services.retrieval_service.query_similar", return_value=[]) as mock_qs:
        retrieval_service.retrieve_text(
            query_embedding=FAKE_EMBEDDING,
            document_ids=["doc_1", "doc_2", "doc_3"],
            top_n=5,
        )

    call_kwargs = mock_qs.call_args
    where_arg = call_kwargs.kwargs.get("where")
    assert where_arg is not None
    where_str = str(where_arg)
    assert "$in" in where_str, "Multiple doc IDs should use $in filter"
    assert "doc_1" in where_str
    assert "doc_3" in where_str


def test_top_n_respected():
    """retrieve_text should pass top_n to query_similar as n_results."""
    with patch("app.services.retrieval_service.query_similar", return_value=[]) as mock_qs:
        retrieval_service.retrieve_text(
            query_embedding=FAKE_EMBEDDING,
            document_ids=None,
            top_n=7,
        )

    call_kwargs = mock_qs.call_args
    n_results_arg = call_kwargs.kwargs.get("n_results")
    assert n_results_arg == 7, f"Expected n_results=7, got {n_results_arg}"
