"""
backend/app/services/telemetry_service.py
Append-only telemetry log + aggregation for GET /metrics.

Storage: data/telemetry.jsonl — one JSON record per line, never truncated (Day 7 scope).

Public API:
  append_record(record: TelemetryRecord) — async, fire-and-forget safe
  compute_metrics(limit=5000)            — read last N records, return MetricsResponse
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List, Optional

import aiofiles

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.telemetry import (
    EmbeddingCost,
    IngestionStats,
    LLMCost,
    MetricsResponse,
    RecentQueryItem,
    StageLatency,
    TelemetryRecord,
)

logger = get_logger(__name__)
settings = get_settings()

import os

# ── Telemetry file path ────────────────────────────────────────────────────────

def _telemetry_path() -> Path:
    """Return path to data/telemetry.jsonl, creating parent dirs as needed."""
    env_path = os.getenv("TELEMETRY_PATH")
    path = Path(env_path) if env_path else Path("./data/telemetry.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ── Write ──────────────────────────────────────────────────────────────────────

async def append_record(record: TelemetryRecord) -> None:
    """
    Append a single TelemetryRecord as a JSON line to data/telemetry.jsonl.

    Non-blocking (async file IO).  Errors are logged but never propagated —
    telemetry failure must not break the query or ingestion pipeline.
    """
    try:
        line = record.model_dump_json() + "\n"
        path = _telemetry_path()
        async with aiofiles.open(path, mode="a", encoding="utf-8") as f:
            await f.write(line)
        logger.debug(
            "Telemetry record appended",
            record_type=record.record_type,
            record_id=record.record_id,
        )
    except Exception as exc:
        logger.warning(
            "Telemetry append failed (non-fatal)",
            error=str(exc),
            record_id=record.record_id,
        )


# ── Read ───────────────────────────────────────────────────────────────────────

async def load_records(limit: int = 5000) -> List[TelemetryRecord]:
    """
    Read the last `limit` records from telemetry.jsonl.

    Returns an empty list if the file does not exist yet.
    Malformed lines are skipped with a warning.
    """
    path = _telemetry_path()
    if not path.exists():
        return []

    records: List[TelemetryRecord] = []
    try:
        async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
            lines = await f.readlines()

        # Take the last `limit` lines to bound memory usage
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(TelemetryRecord.model_validate_json(line))
            except Exception as exc:
                logger.warning("Malformed telemetry line skipped", error=str(exc))

    except Exception as exc:
        logger.warning("Failed to read telemetry file", error=str(exc))

    return records


# ── Aggregate ──────────────────────────────────────────────────────────────────

def _percentile(values: List[float], pct: float) -> float:
    """Compute a percentile (0–100) from a sorted list. Returns 0 if empty."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = math.ceil(pct / 100 * len(sorted_vals)) - 1
    idx = max(0, min(idx, len(sorted_vals) - 1))
    return round(sorted_vals[idx], 2)


async def compute_metrics(
    limit: int = 5000,
    user_id: Optional[str] = None,
) -> MetricsResponse:
    """
    Aggregate data/telemetry.jsonl into a MetricsResponse.

    Reads at most `limit` records (most recent). All monetary values in USD.
    If `user_id` is specified, filters strictly to records owned by that user.
    Records without a user_id are never visible to any user.
    """
    records = await load_records(limit=limit)

    if user_id is not None:
        records = [r for r in records if r.user_id and r.user_id == user_id]
    else:
        # Records without a user_id are never visible to any user
        records = [r for r in records if r.user_id]

    if not records:
        return MetricsResponse()

    query_records = [r for r in records if r.record_type == "query"]
    ingestion_records = [r for r in records if r.record_type == "ingestion"]

    # ── Latency ───────────────────────────────────────────────────────────────
    query_total_ms = [r.latency.total_ms for r in query_records if r.latency.total_ms > 0]
    avg_lat = round(sum(query_total_ms) / len(query_total_ms), 2) if query_total_ms else 0.0
    p50_lat = _percentile(query_total_ms, 50)
    p95_lat = _percentile(query_total_ms, 95)

    def _avg(vals: List[float]) -> float:
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    def _med(vals: List[float]) -> float:
        return _percentile(vals, 50)

    # Average latency by stage (query stages + legacy ade_ms)
    stage = StageLatency(
        embedding_ms=_avg([r.latency.embedding_ms for r in query_records if r.latency.embedding_ms > 0]),
        retrieval_ms=_avg([r.latency.retrieval_ms for r in query_records if r.latency.retrieval_ms > 0]),
        reranking_ms=_avg([r.latency.reranking_ms for r in query_records if r.latency.reranking_ms > 0]),
        llm_ms=_avg([r.latency.llm_ms for r in query_records if r.latency.llm_ms > 0]),
        ade_ms=_avg([r.latency.ade_ms for r in ingestion_records if r.latency.ade_ms > 0]),
    )

    # Median latency by stage (query stages + legacy ade_ms)
    median_stage = StageLatency(
        embedding_ms=_med([r.latency.embedding_ms for r in query_records if r.latency.embedding_ms > 0]),
        retrieval_ms=_med([r.latency.retrieval_ms for r in query_records if r.latency.retrieval_ms > 0]),
        reranking_ms=_med([r.latency.reranking_ms for r in query_records if r.latency.reranking_ms > 0]),
        llm_ms=_med([r.latency.llm_ms for r in query_records if r.latency.llm_ms > 0]),
        ade_ms=_med([r.latency.ade_ms for r in ingestion_records if r.latency.ade_ms > 0]),
    )

    # ── Cache ─────────────────────────────────────────────────────────────────
    cache_hits = sum(1 for r in query_records if r.cache_hit)
    cache_rate = round(cache_hits / len(query_records), 4) if query_records else 0.0

    # ── Tokens & cost ─────────────────────────────────────────────────────────
    total_tokens = sum(r.token_usage.total_tokens for r in records)
    total_embed_cost = round(sum(r.embedding_cost.cost_usd for r in records), 6)
    total_llm_cost = round(sum(r.llm_cost.cost_usd for r in records), 6)
    total_cost = round(total_embed_cost + total_llm_cost, 6)

    # ── Ingestion & ADE stats ─────────────────────────────────────────────────
    total_ade = round(sum(r.ade_credits.per_ingestion for r in ingestion_records), 4)
    ade_durations = [r.latency.ade_ms for r in ingestion_records if r.latency.ade_ms > 0]
    avg_ade = _avg(ade_durations)
    med_ade = _med(ade_durations)

    ingestion_stats = IngestionStats(
        documents_ingested=len(ingestion_records),
        avg_ade_ms=avg_ade,
        median_ade_ms=med_ade,
        total_ade_credits=total_ade,
    )

    # ── Timestamps & Recent Queries (P-4) ─────────────────────────────────────
    timestamps = [r.timestamp.isoformat() for r in records]
    oldest = min(timestamps) if timestamps else None
    newest = max(timestamps) if timestamps else None

    recent_queries = [
        RecentQueryItem(
            id=r.record_id,
            timestamp=r.timestamp.isoformat() if r.timestamp else None,
            question=r.query_preview or "Query",
            model=r.llm_cost.model or r.embedding_cost.model or "",
            total_latency_ms=r.latency.total_ms,
            cache_hit=r.cache_hit,
            total_cost_usd=round(r.llm_cost.cost_usd + r.embedding_cost.cost_usd, 6),
            embedding_ms=r.latency.embedding_ms,
            retrieval_ms=r.latency.retrieval_ms,
            reranking_ms=r.latency.reranking_ms,
            llm_ms=r.latency.llm_ms,
            ade_ms=r.latency.ade_ms,
        )
        for r in reversed(query_records[-50:])
    ]

    return MetricsResponse(
        query_count=len(query_records),
        ingestion_count=len(ingestion_records),
        cache_hit_count=cache_hits,
        cache_hit_rate=cache_rate,
        avg_latency_ms=avg_lat,
        p50_latency_ms=p50_lat,
        median_latency_ms=p50_lat,
        p95_latency_ms=p95_lat,
        latency_by_stage=stage,
        median_latency_by_stage=median_stage,
        p50_latency_by_stage=median_stage,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        total_embedding_cost_usd=total_embed_cost,
        total_llm_cost_usd=total_llm_cost,
        total_ade_credits=total_ade,
        ingestion_stats=ingestion_stats,
        avg_ade_latency_ms=avg_ade,
        median_ade_latency_ms=med_ade,
        records_analyzed=len(records),
        oldest_record_ts=oldest,
        newest_record_ts=newest,
        recent_queries=recent_queries,
    )
