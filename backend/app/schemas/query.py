"""
backend/app/schemas/query.py
Pydantic models for query requests and grounded responses.
Includes RetrievalResult, RerankResult, Source/Grounding, QueryRequest, QueryResponse.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class RouteType(str, Enum):
    TEXT = "text"
    MULTIMODAL = "multimodal"
    HYBRID = "hybrid"


class Source(BaseModel):
    """
    Grounding source — traceable back to a specific chunk in a specific document.
    Implements: answer + exactly where the answer came from.
    """
    document_id: str = Field(..., description="Source document identifier")
    chunk_id: str = Field(..., description="Source chunk identifier")
    page: int = Field(..., description="0-indexed page number")
    bbox: List[float] = Field(
        default_factory=list,
        description="Bounding box [x0, y0, x1, y1] normalized to [0, 1]"
    )
    chunk_type: str = Field(..., description="Content modality: text | table | figure")
    text_preview: str = Field(default="", description="First 200 chars of chunk text for display")
    relevance_score: float = Field(default=0.0, description="Reranker relevance score")
    filename: str = Field(default="", description="Source document filename")


class RetrievalResult(BaseModel):
    """A single candidate from ChromaDB retrieval (pre-reranking)."""
    chunk_id: str
    document_id: str
    chunk_type: str
    page: int
    bbox: List[float]
    text: str
    similarity_score: float


class RerankResult(BaseModel):
    """A single candidate after multimodal reranking."""
    chunk_id: str
    document_id: str
    chunk_type: str
    page: int
    bbox: List[float]
    text: str
    relevance_score: float


class QueryRequest(BaseModel):
    """User query request payload."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language question"
    )
    document_ids: Optional[List[str]] = Field(
        default=None,
        description="Filter retrieval to specific document IDs (None = search all user documents)"
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=20,
        description="Override default rerank_top_k for this query"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What was the total revenue in Q3?",
                "document_ids": ["abc123"],
                "top_k": 5
            }
        }


class LatencyBreakdown(BaseModel):
    """Per-stage latency in milliseconds."""
    total_ms: float = 0.0
    cache_check_ms: float = 0.0
    query_embed_ms: float = 0.0
    retrieval_ms: float = 0.0
    reranking_ms: float = 0.0
    llm_ms: float = 0.0


class QueryResponse(BaseModel):
    """
    Grounded query response.
    The answer is always traceable to source evidence via 'sources'.
    """
    answer: str = Field(..., description="LLM-generated answer grounded in retrieved evidence")
    sources: List[Source] = Field(
        default_factory=list,
        description="Evidence chunks the answer is grounded in"
    )
    route_type: RouteType = Field(..., description="Query route: text | multimodal | hybrid")
    cache_hit: bool = Field(default=False, description="True if answer served from Redis cache")
    model_used: str = Field(default="", description="LLM model that generated the answer")
    provider_used: str = Field(default="", description="Inference provider: groq | openrouter")
    latency: LatencyBreakdown = Field(default_factory=LatencyBreakdown)
    token_usage: dict[str, int] = Field(
        default_factory=dict,
        description="Token counts: {input_tokens, output_tokens, total_tokens}"
    )
    cost_usd: float = Field(default=0.0, description="Estimated cost in USD for this query")

    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "answer": "Total revenue in Q3 was $89.5 billion.",
                "sources": [
                    {
                        "document_id": "abc123",
                        "chunk_id": "c7665222",
                        "page": 12,
                        "bbox": [0.1, 0.2, 0.8, 0.5],
                        "chunk_type": "table"
                    }
                ],
                "route_type": "multimodal",
                "cache_hit": False,
                "model_used": "qwen-qwq-32b",
                "provider_used": "groq"
            }
        }
    }


# ── Auth schemas ──────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")


class UserLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
