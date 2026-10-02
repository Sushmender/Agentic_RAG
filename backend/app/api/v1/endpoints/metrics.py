"""
backend/app/api/v1/endpoints/metrics.py
GET /metrics — aggregated observability dashboard from data/telemetry.jsonl.

No authentication required (open endpoint — suitable for dev/demo).
Returns MetricsResponse covering all 5 Day-7 benchmark categories:
  1. Latency (avg, p95, per-stage)
  2. Token usage
  3. ADE credits
  4. Embedding cost
  5. LLM cost
"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.logging import get_logger
from app.schemas.telemetry import MetricsResponse
from app.services import telemetry_service

logger = get_logger(__name__)
router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get(
    "",
    response_model=MetricsResponse,
    summary="Aggregated observability metrics",
    description=(
        "Returns aggregated pipeline metrics computed from data/telemetry.jsonl. "
        "Covers all 5 Day-7 benchmark categories: latency (avg + p95 per stage), "
        "token usage, ADE credits, embedding cost, and LLM cost. "
        "No authentication required."
    ),
)
async def get_metrics() -> MetricsResponse:
    """
    Aggregate and return all pipeline telemetry metrics.

    Reads from data/telemetry.jsonl (last 5000 records).
    Returns instantly if no telemetry has been recorded yet.
    """
    logger.info("Metrics requested")
    metrics = await telemetry_service.compute_metrics(limit=5000)
    logger.info(
        "Metrics computed",
        query_count=metrics.query_count,
        ingestion_count=metrics.ingestion_count,
        records_analyzed=metrics.records_analyzed,
    )
    return metrics
