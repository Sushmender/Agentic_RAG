"""
backend/app/schemas/telemetry.py
TelemetryRecord — captures all 5 Day-7 benchmark categories per pipeline invocation.

Categories:
  1. latency_ms   — per-stage breakdown: total | ade | embedding | retrieval | reranking | llm
  2. token_usage  — input / output / total tokens for LLM calls
  3. ade_credits  — per-ingestion credit usage (0 for query records)
  4. embedding_cost — model, provider, token_count, cost_usd
  5. llm_cost     — model, provider, input/output tokens, cost_usd

Design:
  - `record_type` = "query" | "ingestion" so callers can filter in /metrics
  - For query records:  ade_credits.per_ingestion = 0, ade_ms = 0
  - For ingestion records: llm_cost fields = 0/empty, retrieval/reranking/llm_ms = 0
  - All monetary fields are in USD
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Sub-models ──────────────────────────────────────────────────────────────────

class LatencyDetail(BaseModel):
    """Per-stage latency in milliseconds."""
    total_ms: float = 0.0
    ade_ms: float = 0.0          # Non-zero only in ingestion records
    embedding_ms: float = 0.0    # Chunk embedding (ingestion) or query embedding (query)
    retrieval_ms: float = 0.0    # Non-zero only in query records
    reranking_ms: float = 0.0   # Non-zero only in query records
    llm_ms: float = 0.0          # Non-zero only in query records


class TokenUsage(BaseModel):
    """LLM token consumption for this record."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ADECredits(BaseModel):
    """ADE document parsing credit usage."""
    per_ingestion: float = 0.0   # Credits consumed by this ingestion call
    cumulative: float = 0.0      # Running total (computed at /metrics time from telemetry.jsonl)


class EmbeddingCost(BaseModel):
    """Embedding API cost breakdown."""
    model: str = ""
    provider: str = "openrouter"
    token_count: int = 0
    cost_usd: float = 0.0


class LLMCost(BaseModel):
    """LLM inference cost breakdown."""
    model: str = ""
    provider: str = ""           # "groq" | "openrouter"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


# ── Main record ──────────────────────────────────────────────────────────────────

class TelemetryRecord(BaseModel):
    """
    One telemetry record per pipeline invocation (query or ingestion).
    Appended as a JSON line to data/telemetry.jsonl.
    """
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    record_type: str = Field(
        ...,
        description="'query' or 'ingestion'",
        pattern="^(query|ingestion)$",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    request_id: str = Field(default="", description="X-Request-ID from middleware")
    user_id: str = Field(default="", description="Authenticated user ID")

    # Query-specific (empty/None for ingestion records)
    query_preview: Optional[str] = Field(
        default=None,
        description="First 80 chars of the query (query records only)",
    )
    route_type: Optional[str] = Field(
        default=None,
        description="text | multimodal | hybrid (query records only)",
    )
    cache_hit: bool = Field(
        default=False,
        description="True if answer was served from Redis cache",
    )

    # Ingestion-specific (empty/None for query records)
    document_id: Optional[str] = Field(
        default=None,
        description="Document ID (ingestion records only)",
    )

    # ── The 5 benchmark categories ────────────────────────────────────────────
    latency: LatencyDetail = Field(default_factory=LatencyDetail)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    ade_credits: ADECredits = Field(default_factory=ADECredits)
    embedding_cost: EmbeddingCost = Field(default_factory=EmbeddingCost)
    llm_cost: LLMCost = Field(default_factory=LLMCost)

    model_config = {"protected_namespaces": ()}


# ── Aggregated metrics response ──────────────────────────────────────────────────

class StageLatency(BaseModel):
    """Average latency per pipeline stage (for /metrics response)."""
    embedding_ms: float = 0.0
    retrieval_ms: float = 0.0
    reranking_ms: float = 0.0
    llm_ms: float = 0.0
    ade_ms: float = 0.0


class MetricsResponse(BaseModel):
    """
    Aggregated metrics response from GET /metrics.
    Computed from data/telemetry.jsonl.
    """
    # Counts
    query_count: int = 0
    ingestion_count: int = 0
    cache_hit_count: int = 0
    cache_hit_rate: float = 0.0         # cache_hit_count / query_count

    # Latency
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    latency_by_stage: StageLatency = Field(default_factory=StageLatency)

    # Tokens & cost
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_embedding_cost_usd: float = 0.0
    total_llm_cost_usd: float = 0.0

    # ADE
    total_ade_credits: float = 0.0

    # Meta
    records_analyzed: int = 0
    oldest_record_ts: Optional[str] = None
    newest_record_ts: Optional[str] = None
