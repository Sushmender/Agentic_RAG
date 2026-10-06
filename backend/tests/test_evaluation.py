"""
backend/tests/test_evaluation.py
Tests for Day 8 — RAG Evaluation (Recall@K, Precision@K, gold dataset, pipeline).

Tests are structured in three groups:
  1. Unit tests for recall_at_k() and precision_at_k() metric functions
  2. Unit tests for gold_dataset (load / generate)
  3. Integration-style test for evaluate_pipeline() with mocked providers
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.evaluation.evaluator import precision_at_k, recall_at_k
from app.evaluation.gold_dataset import (
    _extract_table_title,
    _extract_topic,
    _question_from_chunk,
    load,
    save,
)


# ── 1. Metric unit tests ───────────────────────────────────────────────────────

class TestRecallAtK:
    """Unit tests for recall_at_k()."""

    def test_perfect_recall(self):
        """All expected IDs are in Top-K → recall = 1.0"""
        retrieved = ["c1", "c2", "c3", "c4", "c5"]
        expected  = ["c1", "c2"]
        assert recall_at_k(retrieved, expected, k=5) == 1.0

    def test_partial_recall(self):
        """Half of expected found in Top-K → recall = 0.5"""
        retrieved = ["c1", "c3", "c4", "c5", "c6"]
        expected  = ["c1", "c2"]
        assert recall_at_k(retrieved, expected, k=5) == 0.5

    def test_zero_recall(self):
        """None of expected in Top-K → recall = 0.0"""
        retrieved = ["c3", "c4", "c5"]
        expected  = ["c1", "c2"]
        assert recall_at_k(retrieved, expected, k=5) == 0.0

    def test_empty_expected_returns_zero(self):
        """If no expected IDs defined → return 0.0 (undefined → zero)."""
        retrieved = ["c1", "c2", "c3"]
        expected: List[str] = []
        assert recall_at_k(retrieved, expected, k=5) == 0.0

    def test_k_smaller_than_retrieved(self):
        """Only Top-K are considered, even if more retrieved."""
        retrieved = ["c99", "c1", "c2"]
        expected  = ["c1"]
        # c1 is at rank 2 (index 1) — inside Top-2
        assert recall_at_k(retrieved, expected, k=2) == 1.0

    def test_k_equals_one(self):
        """K=1: only the top result matters."""
        retrieved = ["c1", "c2"]
        expected  = ["c1"]
        assert recall_at_k(retrieved, expected, k=1) == 1.0

    def test_k_equals_one_miss(self):
        retrieved = ["c99", "c1"]
        expected  = ["c1"]
        assert recall_at_k(retrieved, expected, k=1) == 0.0


class TestPrecisionAtK:
    """Unit tests for precision_at_k()."""

    def test_perfect_precision(self):
        """All Top-K are expected → precision = 1.0"""
        retrieved = ["c1", "c2", "c3", "c4", "c5"]
        expected  = ["c1", "c2", "c3", "c4", "c5"]
        assert precision_at_k(retrieved, expected, k=5) == 1.0

    def test_partial_precision(self):
        """2 of Top-5 are expected → precision = 0.4"""
        retrieved = ["c1", "c2", "x1", "x2", "x3"]
        expected  = ["c1", "c2", "c3"]
        assert precision_at_k(retrieved, expected, k=5) == pytest.approx(0.4)

    def test_zero_precision(self):
        """None of Top-K are expected → precision = 0.0"""
        retrieved = ["x1", "x2", "x3"]
        expected  = ["c1", "c2"]
        assert precision_at_k(retrieved, expected, k=3) == 0.0

    def test_k_zero_returns_zero(self):
        """K=0 is undefined → return 0.0"""
        retrieved = ["c1"]
        expected  = ["c1"]
        assert precision_at_k(retrieved, expected, k=0) == 0.0

    def test_k_equals_one_hit(self):
        retrieved = ["c1", "c2"]
        expected  = ["c1"]
        assert precision_at_k(retrieved, expected, k=1) == 1.0

    def test_k_equals_one_miss(self):
        retrieved = ["c99", "c1"]
        expected  = ["c1"]
        assert precision_at_k(retrieved, expected, k=1) == 0.0


# ── 2. Gold dataset unit tests ─────────────────────────────────────────────────

class TestGoldDatasetHelpers:
    """Unit tests for internal helpers in gold_dataset.py."""

    def test_extract_topic_from_plain_text(self):
        text = "Revenue Overview\n\nQ3 revenue was $89.5 billion."
        result = _extract_topic(text)
        assert "Revenue" in result

    def test_extract_topic_strips_html(self):
        text = "<a id='abc'></a>\n\n# Budget Report Title"
        result = _extract_topic(text)
        # Should strip the anchor tag and markdown heading
        assert "Budget Report Title" in result

    def test_extract_table_title(self):
        text = "<a id='xyz'></a>\n\nBudget vs. Actual Spend\n<table><tr><td>A</td></tr></table>"
        result = _extract_table_title(text)
        assert "Budget vs. Actual Spend" in result

    def test_question_from_text_chunk(self):
        chunk = {
            "chunk_type": "text",
            "text": "Annual Revenue Report\nRevenue in Q3 was $89.5B.",
            "page": 0,
            "chunk_id": "abc",
        }
        q = _question_from_chunk(chunk)
        assert q is not None
        assert "Annual Revenue Report" in q or "section about" in q

    def test_question_from_table_chunk(self):
        chunk = {
            "chunk_type": "table",
            "text": "<a id='t1'></a>\n\nDepartment Budget\n<table><tr><td>Eng</td></tr></table>",
            "page": 0,
            "chunk_id": "t1",
        }
        q = _question_from_chunk(chunk)
        assert q is not None
        assert "Department Budget" in q or "table" in q.lower()

    def test_question_from_figure_chunk(self):
        chunk = {
            "chunk_type": "figure",
            "text": "Figure: Revenue growth chart.",
            "page": 2,
            "chunk_id": "f1",
        }
        q = _question_from_chunk(chunk)
        assert q is not None
        assert "page 3" in q.lower() or "figure" in q.lower()

    def test_question_from_empty_chunk_returns_none(self):
        chunk = {"chunk_type": "text", "text": "", "page": 0, "chunk_id": "x"}
        assert _question_from_chunk(chunk) is None


class TestGoldDatasetIO:
    """Tests for gold dataset save/load."""

    def test_save_and_load(self, tmp_path, monkeypatch):
        """Saving then loading returns the same dataset."""
        import app.evaluation.gold_dataset as gd_module

        test_path = tmp_path / "gold_dataset.json"
        monkeypatch.setattr(gd_module, "GOLD_DATASET_PATH", test_path)

        dataset = [
            {
                "question": "What is the budget?",
                "expected_document_ids": ["doc123"],
                "expected_chunk_ids": ["chunk456"],
            }
        ]
        save(dataset)
        loaded = load()

        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0]["question"] == "What is the budget?"
        assert loaded[0]["expected_chunk_ids"] == ["chunk456"]

    def test_load_returns_none_if_no_file(self, tmp_path, monkeypatch):
        """load() returns None when file does not exist."""
        import app.evaluation.gold_dataset as gd_module

        monkeypatch.setattr(gd_module, "GOLD_DATASET_PATH", tmp_path / "nonexistent.json")
        assert load() is None


# ── 3. evaluate_pipeline() integration (mocked providers) ─────────────────────

class TestEvaluatePipeline:
    """
    Test evaluate_pipeline() with mocked embedding and reranker providers.
    We mock:
      - embedding_provider.embed_query → returns a dummy vector
      - retrieve_hybrid → returns candidate chunks
      - reranker_provider.rerank → returns reranked (same order for simplicity)
    """

    GOLD = [
        {
            "question": "What are the budget figures?",
            "expected_document_ids": ["doc1"],
            "expected_chunk_ids": ["c1"],
        }
    ]

    @pytest.mark.asyncio
    async def test_evaluate_pipeline_structure(self):
        """Result has correct top-level keys."""
        from app.evaluation.evaluator import evaluate_pipeline

        dummy_embedding = [0.1] * 10

        with (
            patch(
                "app.evaluation.evaluator.embedding_provider.embed_query",
                new=AsyncMock(return_value=dummy_embedding),
            ),
            patch(
                "app.evaluation.evaluator.retrieve_hybrid",
                return_value=[
                    MagicMock(
                        chunk_id="c1",
                        document_id="doc1",
                        chunk_type="text",
                        page=0,
                        bbox=[0, 0, 1, 1],
                        text="Budget info",
                        similarity_score=0.9,
                    )
                ],
            ),
            patch(
                "app.evaluation.evaluator.reranker_provider.rerank",
                new=AsyncMock(return_value=[{"chunk_id": "c1", "relevance_score": 0.95}]),
            ),
        ):
            report = await evaluate_pipeline(self.GOLD, k=5)

        assert "k" in report
        assert "pre_rerank" in report
        assert "post_rerank" in report
        assert "per_question" in report
        assert "questions_evaluated" in report
        assert report["k"] == 5

    @pytest.mark.asyncio
    async def test_evaluate_pipeline_perfect_hit(self):
        """When expected chunk is retrieved and reranked first → both recall = 1.0"""
        from app.evaluation.evaluator import evaluate_pipeline

        dummy_embedding = [0.1] * 10

        with (
            patch(
                "app.evaluation.evaluator.embedding_provider.embed_query",
                new=AsyncMock(return_value=dummy_embedding),
            ),
            patch(
                "app.evaluation.evaluator.retrieve_hybrid",
                return_value=[
                    MagicMock(
                        chunk_id="c1",
                        document_id="doc1",
                        chunk_type="text",
                        page=0,
                        bbox=[0, 0, 1, 1],
                        text="Budget info",
                        similarity_score=0.9,
                    )
                ],
            ),
            patch(
                "app.evaluation.evaluator.reranker_provider.rerank",
                new=AsyncMock(return_value=[{"chunk_id": "c1", "relevance_score": 0.95}]),
            ),
        ):
            report = await evaluate_pipeline(self.GOLD, k=5)

        assert report["pre_rerank"]["recall_at_k"] == 1.0
        assert report["post_rerank"]["recall_at_k"] == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_pipeline_miss(self):
        """When expected chunk is NOT retrieved → both recall = 0.0"""
        from app.evaluation.evaluator import evaluate_pipeline

        dummy_embedding = [0.1] * 10

        with (
            patch(
                "app.evaluation.evaluator.embedding_provider.embed_query",
                new=AsyncMock(return_value=dummy_embedding),
            ),
            patch(
                "app.evaluation.evaluator.retrieve_hybrid",
                return_value=[
                    MagicMock(
                        chunk_id="wrong_chunk",
                        document_id="doc1",
                        chunk_type="text",
                        page=0,
                        bbox=[0, 0, 1, 1],
                        text="Other info",
                        similarity_score=0.3,
                    )
                ],
            ),
            patch(
                "app.evaluation.evaluator.reranker_provider.rerank",
                new=AsyncMock(
                    return_value=[{"chunk_id": "wrong_chunk", "relevance_score": 0.3}]
                ),
            ),
        ):
            report = await evaluate_pipeline(self.GOLD, k=5)

        assert report["pre_rerank"]["recall_at_k"] == 0.0
        assert report["post_rerank"]["recall_at_k"] == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_pipeline_empty_gold(self):
        """Empty gold dataset → returns zero report."""
        from app.evaluation.evaluator import evaluate_pipeline

        report = await evaluate_pipeline([], k=5)

        assert report["questions_evaluated"] == 0
        assert report["pre_rerank"]["recall_at_k"] == 0.0
        assert report["post_rerank"]["recall_at_k"] == 0.0
