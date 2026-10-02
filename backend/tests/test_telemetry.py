"""
backend/tests/test_telemetry.py
Tests for Day 7 telemetry: TelemetryRecord schema, append/load, and GET /metrics.

Coverage:
  - TelemetryRecord populated with all 5 benchmark categories for query records
  - TelemetryRecord populated with all 5 benchmark categories for ingestion records
  - append_record() writes to telemetry.jsonl
  - load_records() parses records back correctly
  - compute_metrics() returns correct aggregation shape
  - GET /metrics returns 200 with all expected fields
  - Cache hit records counted correctly
  - p95 computation with multiple records
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.schemas.telemetry import (
    ADECredits,
    EmbeddingCost,
    LatencyDetail,
    LLMCost,
    MetricsResponse,
    TelemetryRecord,
    TokenUsage,
)
from app.services import telemetry_service


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_telemetry_file(tmp_path, monkeypatch):
    """Redirect telemetry.jsonl to a temp file for test isolation."""
    tel_path = tmp_path / "telemetry.jsonl"
    # Patch the _telemetry_path function to return the temp path
    monkeypatch.setattr(
        telemetry_service,
        "_telemetry_path",
        lambda: tel_path,
    )
    return tel_path


def _make_query_record(**overrides) -> TelemetryRecord:
    """Build a minimal valid query TelemetryRecord."""
    defaults = dict(
        record_type="query",
        user_id="user-test",
        query_preview="What is the revenue?",
        route_type="text",
        cache_hit=False,
        latency=LatencyDetail(
            total_ms=1200.0,
            embedding_ms=120.0,
            retrieval_ms=80.0,
            reranking_ms=200.0,
            llm_ms=800.0,
        ),
        token_usage=TokenUsage(input_tokens=500, output_tokens=200, total_tokens=700),
        embedding_cost=EmbeddingCost(model="nvidia/llama-nemotron-embed-vl-1b-v2:free", provider="openrouter", token_count=0, cost_usd=0.0),
        llm_cost=LLMCost(model="qwen/qwen3.8-27b", provider="groq", input_tokens=500, output_tokens=200, cost_usd=0.000350),
    )
    defaults.update(overrides)
    return TelemetryRecord(**defaults)


def _make_ingestion_record(**overrides) -> TelemetryRecord:
    """Build a minimal valid ingestion TelemetryRecord."""
    defaults = dict(
        record_type="ingestion",
        user_id="user-test",
        document_id="doc-abc123",
        latency=LatencyDetail(
            total_ms=5000.0,
            ade_ms=4500.0,
            embedding_ms=500.0,
        ),
        ade_credits=ADECredits(per_ingestion=3.0),
        embedding_cost=EmbeddingCost(model="nvidia/llama-nemotron-embed-vl-1b-v2:free", provider="openrouter", token_count=150, cost_usd=0.0),
    )
    defaults.update(overrides)
    return TelemetryRecord(**defaults)


# ── Schema tests ───────────────────────────────────────────────────────────────

class TestTelemetrySchema:
    def test_query_record_has_all_5_categories(self):
        """TelemetryRecord must expose all 5 benchmark category fields."""
        rec = _make_query_record()
        # 1. Latency
        assert rec.latency.total_ms == 1200.0
        assert rec.latency.embedding_ms == 120.0
        assert rec.latency.retrieval_ms == 80.0
        assert rec.latency.reranking_ms == 200.0
        assert rec.latency.llm_ms == 800.0
        assert rec.latency.ade_ms == 0.0  # Q3 answer: 0 for query records
        # 2. Token usage
        assert rec.token_usage.input_tokens == 500
        assert rec.token_usage.output_tokens == 200
        assert rec.token_usage.total_tokens == 700
        # 3. ADE credits (zero for query)
        assert rec.ade_credits.per_ingestion == 0.0
        # 4. Embedding cost
        assert rec.embedding_cost.model != ""
        # 5. LLM cost
        assert rec.llm_cost.cost_usd == pytest.approx(0.000350, rel=1e-3)
        assert rec.llm_cost.provider == "groq"

    def test_ingestion_record_has_all_5_categories(self):
        rec = _make_ingestion_record()
        # 1. Latency — ade_ms populated
        assert rec.latency.ade_ms == 4500.0
        assert rec.latency.embedding_ms == 500.0
        assert rec.latency.llm_ms == 0.0  # no LLM in ingestion
        # 3. ADE credits — populated
        assert rec.ade_credits.per_ingestion == 3.0
        # 5. LLM cost — empty for ingestion
        assert rec.llm_cost.cost_usd == 0.0

    def test_record_type_validation(self):
        """Only 'query' and 'ingestion' are valid record types."""
        with pytest.raises(Exception):
            TelemetryRecord(record_type="unknown")

    def test_query_record_serialization_roundtrip(self):
        """Records must survive JSON serialization for telemetry.jsonl storage."""
        rec = _make_query_record()
        json_str = rec.model_dump_json()
        restored = TelemetryRecord.model_validate_json(json_str)
        assert restored.record_id == rec.record_id
        assert restored.latency.total_ms == rec.latency.total_ms
        assert restored.llm_cost.cost_usd == rec.llm_cost.cost_usd


# ── Service tests ──────────────────────────────────────────────────────────────

class TestTelemetryService:
    @pytest.mark.asyncio
    async def test_append_record_writes_jsonl(self, isolated_telemetry_file):
        """append_record() must write exactly one JSON line per call."""
        rec = _make_query_record()
        await telemetry_service.append_record(rec)

        lines = isolated_telemetry_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["record_id"] == rec.record_id
        assert parsed["record_type"] == "query"

    @pytest.mark.asyncio
    async def test_append_multiple_records(self, isolated_telemetry_file):
        """Multiple appends produce multiple lines."""
        for _ in range(3):
            await telemetry_service.append_record(_make_query_record())

        lines = isolated_telemetry_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

    @pytest.mark.asyncio
    async def test_load_records_empty_file(self, isolated_telemetry_file):
        """load_records returns empty list when file is missing."""
        # File doesn't exist yet
        assert not isolated_telemetry_file.exists()
        records = await telemetry_service.load_records()
        assert records == []

    @pytest.mark.asyncio
    async def test_load_records_after_append(self, isolated_telemetry_file):
        """load_records correctly parses appended records."""
        q = _make_query_record()
        i = _make_ingestion_record()
        await telemetry_service.append_record(q)
        await telemetry_service.append_record(i)

        records = await telemetry_service.load_records()
        assert len(records) == 2
        types = {r.record_type for r in records}
        assert types == {"query", "ingestion"}

    @pytest.mark.asyncio
    async def test_append_error_does_not_raise(self, monkeypatch):
        """Telemetry failure must never propagate (fire-and-forget)."""
        # Make the file open fail
        async def _bad_open(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("aiofiles.open", _bad_open)
        # Should NOT raise
        await telemetry_service.append_record(_make_query_record())


# ── Aggregation tests ──────────────────────────────────────────────────────────

class TestComputeMetrics:
    @pytest.mark.asyncio
    async def test_empty_telemetry_returns_zeros(self, isolated_telemetry_file):
        """compute_metrics on empty file returns zeroed MetricsResponse."""
        m = await telemetry_service.compute_metrics()
        assert isinstance(m, MetricsResponse)
        assert m.query_count == 0
        assert m.ingestion_count == 0
        assert m.total_cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_query_count_and_cache_hit_rate(self, isolated_telemetry_file):
        """Cache hit rate = hits / total queries."""
        await telemetry_service.append_record(_make_query_record(cache_hit=False))
        await telemetry_service.append_record(_make_query_record(cache_hit=False))
        await telemetry_service.append_record(_make_query_record(cache_hit=True))

        m = await telemetry_service.compute_metrics()
        assert m.query_count == 3
        assert m.cache_hit_count == 1
        assert m.cache_hit_rate == pytest.approx(1 / 3, rel=1e-3)

    @pytest.mark.asyncio
    async def test_avg_latency_computed_correctly(self, isolated_telemetry_file):
        """avg_latency_ms should be the mean of query records' total_ms."""
        await telemetry_service.append_record(
            _make_query_record(latency=LatencyDetail(total_ms=1000.0))
        )
        await telemetry_service.append_record(
            _make_query_record(latency=LatencyDetail(total_ms=2000.0))
        )

        m = await telemetry_service.compute_metrics()
        assert m.avg_latency_ms == pytest.approx(1500.0, rel=1e-3)

    @pytest.mark.asyncio
    async def test_p95_latency(self, isolated_telemetry_file):
        """p95 should return 95th-percentile of total_ms from query records."""
        for ms in [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 9000.0]:
            await telemetry_service.append_record(
                _make_query_record(latency=LatencyDetail(total_ms=ms))
            )
        m = await telemetry_service.compute_metrics()
        # p95 of 10 values = 95th percentile ~ 9000.0
        assert m.p95_latency_ms >= 900.0

    @pytest.mark.asyncio
    async def test_ade_credits_summed_from_ingestion_records(self, isolated_telemetry_file):
        """total_ade_credits sums per_ingestion from ingestion records only."""
        await telemetry_service.append_record(_make_ingestion_record())  # 3.0 credits
        await telemetry_service.append_record(_make_ingestion_record())  # 3.0 credits
        await telemetry_service.append_record(_make_query_record())      # 0 credits

        m = await telemetry_service.compute_metrics()
        assert m.total_ade_credits == pytest.approx(6.0, rel=1e-3)
        assert m.ingestion_count == 2

    @pytest.mark.asyncio
    async def test_total_tokens_and_cost(self, isolated_telemetry_file):
        """Total tokens and costs are summed across all records."""
        await telemetry_service.append_record(_make_query_record())  # 700 tokens, $0.00035
        await telemetry_service.append_record(_make_query_record())  # 700 tokens, $0.00035

        m = await telemetry_service.compute_metrics()
        assert m.total_tokens == 1400
        assert m.total_llm_cost_usd == pytest.approx(0.000700, rel=1e-2)

    @pytest.mark.asyncio
    async def test_records_analyzed_field(self, isolated_telemetry_file):
        """records_analyzed should count all records read from file."""
        for _ in range(5):
            await telemetry_service.append_record(_make_query_record())
        m = await telemetry_service.compute_metrics()
        assert m.records_analyzed == 5


# ── API endpoint tests ─────────────────────────────────────────────────────────

class TestMetricsEndpoint:
    @pytest.mark.asyncio
    async def test_get_metrics_returns_200(self, isolated_telemetry_file):
        """GET /metrics must return 200 with a MetricsResponse-shaped body."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/metrics")

        assert resp.status_code == 200
        data = resp.json()
        # Must have all top-level keys
        for key in [
            "query_count", "ingestion_count", "cache_hit_count", "cache_hit_rate",
            "avg_latency_ms", "p95_latency_ms", "latency_by_stage",
            "total_tokens", "total_cost_usd",
            "total_embedding_cost_usd", "total_llm_cost_usd",
            "total_ade_credits", "records_analyzed",
        ]:
            assert key in data, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_get_metrics_no_auth_required(self, isolated_telemetry_file):
        """GET /metrics must be accessible without a JWT token."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # No Authorization header
            resp = await client.get("/api/v1/metrics")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_metrics_with_real_data(self, isolated_telemetry_file):
        """GET /metrics returns non-zero counts after telemetry records are appended."""
        # Pre-populate telemetry
        await telemetry_service.append_record(_make_query_record())
        await telemetry_service.append_record(_make_ingestion_record())

        from httpx import AsyncClient, ASGITransport
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/metrics")

        data = resp.json()
        assert data["query_count"] == 1
        assert data["ingestion_count"] == 1
        assert data["total_ade_credits"] == pytest.approx(3.0, rel=1e-3)
        assert data["records_analyzed"] == 2
