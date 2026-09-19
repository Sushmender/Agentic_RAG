"""
backend/tests/test_chunking.py
Unit tests for chunking_service.normalize_chunks().

All tests are fully mocked — zero ADE credits consumed.
Covers: text/table/figure normalization, empty filtering,
        idempotent chunk_id generation, bbox mapping, confidence.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from app.services.chunking_service import normalize_chunks, parse_ade_metadata, _stable_chunk_id
from app.schemas.chunk import ChunkType


# ── Fixture helpers ────────────────────────────────────────────────────────────

DOCUMENT_ID = "abc123"
SOURCE = "test_doc.pdf"
PARSER_VERSION = "dpt-2-20260410"

def _make_ade_result(chunks: list[dict], credit_usage: float = 2.0) -> dict:
    """Build a minimal ADE-shaped result dict from a list of raw chunk dicts."""
    return {
        "chunks": chunks,
        "markdown": "\n\n".join(c.get("markdown", "") for c in chunks),
        "metadata": {
            "credit_usage": credit_usage,
            "version": PARSER_VERSION,
            "page_count": 1,
            "job_id": "test-job-001",
            "duration_ms": 1234,
            "failed_pages": [],
            "filename": SOURCE,
        },
        "grounding": {
            c["id"]: {
                "box": c["grounding"]["box"],
                "page": c["grounding"]["page"],
                "type": f"chunk{c['type'].capitalize()}",
                "confidence": 0.99,
                "low_confidence_spans": [],
            }
            for c in chunks
        },
        "splits": [],
    }


def _text_chunk(
    chunk_id: str = "chunk-text-001",
    page: int = 0,
    text: str = "Hello world",
) -> dict:
    return {
        "id": chunk_id,
        "type": "text",
        "markdown": f"<a id='{chunk_id}'></a>\n\n{text}",
        "grounding": {
            "box": {"left": 0.1, "top": 0.05, "right": 0.9, "bottom": 0.15},
            "page": page,
        },
    }


def _table_chunk(
    chunk_id: str = "chunk-table-001",
    page: int = 0,
) -> dict:
    html = "<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>"
    return {
        "id": chunk_id,
        "type": "table",
        "markdown": f"<a id='{chunk_id}'></a>\n\nRegional Data\n{html}",
        "grounding": {
            "box": {"left": 0.12, "top": 0.25, "right": 0.83, "bottom": 0.45},
            "page": page,
        },
    }


def _figure_chunk(
    chunk_id: str = "chunk-fig-001",
    page: int = 0,
) -> dict:
    chart_text = "<::Bar chart\nX: Q1 Q2 Q3\nData: 100 150 200\n: chart::>"
    return {
        "id": chunk_id,
        "type": "figure",
        "markdown": f"<a id='{chunk_id}'></a>\n\nQuarterly Trend\n{chart_text}",
        "grounding": {
            "box": {"left": 0.11, "top": 0.47, "right": 0.77, "bottom": 0.73},
            "page": page,
        },
    }


def _empty_chunk(chunk_id: str = "chunk-empty-001") -> dict:
    return {
        "id": chunk_id,
        "type": "text",
        "markdown": "   \n\n   ",
        "grounding": {
            "box": {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0},
            "page": 0,
        },
    }


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestNormalizeChunks:

    def test_empty_ade_result_returns_empty_list(self):
        result = normalize_chunks(
            {"chunks": [], "metadata": {"version": "v1", "credit_usage": 0.0}, "grounding": {}},
            document_id=DOCUMENT_ID,
            source=SOURCE,
        )
        assert result == []

    def test_text_chunk_basic_fields(self):
        raw = _make_ade_result([_text_chunk()])
        chunks = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)

        assert len(chunks) == 1
        c = chunks[0]
        assert c.chunk_type == ChunkType.TEXT
        assert c.document_id == DOCUMENT_ID
        assert c.source == SOURCE
        assert c.parser_version == PARSER_VERSION
        assert c.page == 0
        assert "Hello world" in c.text
        assert len(c.bbox) == 4
        assert c.bbox[0] == pytest.approx(0.1)   # left = x0
        assert c.bbox[1] == pytest.approx(0.05)  # top  = y0
        assert c.bbox[2] == pytest.approx(0.9)   # right = x1
        assert c.bbox[3] == pytest.approx(0.15)  # bottom = y1

    def test_table_chunk_preserves_html(self):
        raw = _make_ade_result([_table_chunk()])
        chunks = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)

        assert len(chunks) == 1
        c = chunks[0]
        assert c.chunk_type == ChunkType.TABLE
        # HTML table must be preserved — not flattened
        assert "<table>" in c.text
        assert "<td>" in c.text

    def test_figure_chunk_preserves_description(self):
        raw = _make_ade_result([_figure_chunk()])
        chunks = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)

        assert len(chunks) == 1
        c = chunks[0]
        assert c.chunk_type == ChunkType.FIGURE
        # Figure chart syntax preserved
        assert "chart" in c.text.lower() or "Quarterly" in c.text

    def test_empty_chunks_filtered_out(self):
        raw = _make_ade_result([_text_chunk(), _empty_chunk(), _table_chunk()])
        chunks = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)

        # Only 2 non-empty chunks should survive
        assert len(chunks) == 2
        types = {c.chunk_type for c in chunks}
        assert ChunkType.TEXT in types
        assert ChunkType.TABLE in types

    def test_chunk_id_is_deterministic(self):
        """Same input always produces same chunk_id."""
        raw = _make_ade_result([_text_chunk(page=1)])
        chunks_a = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)
        chunks_b = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)

        assert chunks_a[0].chunk_id == chunks_b[0].chunk_id

    def test_chunk_id_differs_by_page(self):
        raw = _make_ade_result([
            _text_chunk(chunk_id="c1", page=0),
            _text_chunk(chunk_id="c2", page=1),
        ])
        chunks = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)
        assert chunks[0].chunk_id != chunks[1].chunk_id

    def test_ade_chunk_id_preserved(self):
        """ADE's own UUID is stored in ade_chunk_id for future UI grounding."""
        ade_uuid = "b5b47447-fb2a-408c-a9f9-90f3f60ea5c3"
        raw = _make_ade_result([_text_chunk(chunk_id=ade_uuid)])
        chunks = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)
        assert chunks[0].ade_chunk_id == ade_uuid

    def test_confidence_extracted_from_grounding_map(self):
        raw = _make_ade_result([_text_chunk()])
        chunks = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)
        # Grounding map in fixture sets confidence=0.99
        assert chunks[0].confidence == pytest.approx(0.99)

    def test_mixed_chunk_types(self):
        raw = _make_ade_result([_text_chunk(), _table_chunk(), _figure_chunk()])
        chunks = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)

        assert len(chunks) == 3
        types = [c.chunk_type for c in chunks]
        assert ChunkType.TEXT in types
        assert ChunkType.TABLE in types
        assert ChunkType.FIGURE in types

    def test_idempotency_via_json_roundtrip(self):
        """
        Loading chunks from chunks.json and re-normalizing from the same
        raw.json must produce identical chunk_ids.
        This simulates the ADE cache-hit path in ingestion_service.
        """
        raw = _make_ade_result([_text_chunk(), _table_chunk()])
        chunks_first_run = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)

        # Simulate persist + reload
        chunk_dicts = [c.model_dump() for c in chunks_first_run]
        reloaded_ids = [d["chunk_id"] for d in chunk_dicts]

        # Re-normalize from same raw (simulates cold-start with same doc)
        chunks_second_run = normalize_chunks(raw, document_id=DOCUMENT_ID, source=SOURCE)
        second_ids = [c.chunk_id for c in chunks_second_run]

        assert reloaded_ids == second_ids


class TestParseAdeMetadata:

    def test_extracts_all_fields(self):
        raw = _make_ade_result([_text_chunk()], credit_usage=3.5)
        meta = parse_ade_metadata(raw)
        assert meta["parser_version"] == PARSER_VERSION
        assert meta["page_count"] == 1
        assert meta["credit_usage"] == pytest.approx(3.5)
        assert meta["ade_job_id"] == "test-job-001"
        assert meta["duration_ms"] == 1234
        assert meta["failed_pages"] == []

    def test_missing_metadata_returns_defaults(self):
        meta = parse_ade_metadata({})
        assert meta["parser_version"] == "unknown"
        assert meta["page_count"] == 0
        assert meta["credit_usage"] == pytest.approx(0.0)
