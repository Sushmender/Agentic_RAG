"""
backend/app/api/v1/endpoints/query.py
Query endpoint — multimodal RAG pipeline.

Day 4: Route → Embed query → Retrieve Top-N → return candidate sources.
       Answer field contains a Day-4 placeholder (LLM generation is Day 5).
Day 5: Full pipeline — Rerank → Assemble context → Generate grounded answer.
Day 6: Redis cache check before pipeline.
"""
from __future__ import annotations

import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.logging import get_logger
from app.core.security import get_current_user_id
from app.providers.openrouter_embedding import embedding_provider
from app.schemas.query import (
    LatencyBreakdown,
    QueryRequest,
    QueryResponse,
    RetrievalResult,
    RouteType,
    Source,
)
from app.services.query_router import route_query
from app.services.retrieval_service import (
    DEFAULT_TOP_N,
    retrieve_hybrid,
    retrieve_multimodal,
    retrieve_text,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/query", tags=["Query"])


@router.post(
    "",
    response_model=QueryResponse,
    summary="Ask a question about ingested documents",
    description=(
        "Runs the multimodal RAG pipeline: "
        "route → embed → retrieve → (rerank Day 5) → (generate Day 5). "
        "Day 4: returns Top-N retrieval candidates with a placeholder answer. "
        "Checks Redis cache first (Day 6). Returns grounded answer with source citations."
    ),
)
async def query(
    request: QueryRequest,
    user_id: str = Depends(get_current_user_id),
) -> QueryResponse:
    """
    Day 4 implementation: route + embed + retrieve.
    Returns pre-rerank candidates as sources with a placeholder answer string.
    Full LLM answer and reranking wired in Day 5.
    """
    pipeline_start = time.monotonic()
    top_n = request.top_k or DEFAULT_TOP_N

    log = logger.bind(user_id=user_id, query_preview=request.query[:80])
    log_kwargs: dict = {"top_n": top_n}
    if request.document_ids:
        log_kwargs["document_ids"] = request.document_ids
    log.info("Query received", **log_kwargs)

    # ── Step 1: Classify query → RouteType ───────────────────────────────────
    route = route_query(request.query)

    # ── Step 2: Embed query in query mode ────────────────────────────────────
    embed_start = time.monotonic()
    try:
        query_embedding = await embedding_provider.embed_query(request.query)
    except Exception as exc:
        log.error("Query embedding failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Embedding provider error: {exc}",
        ) from exc
    embed_ms = round((time.monotonic() - embed_start) * 1000, 1)

    # ── Step 3: Retrieve Top-N candidates ────────────────────────────────────
    retrieval_start = time.monotonic()
    try:
        candidates: List[RetrievalResult] = _run_retrieval(
            route=route,
            query_embedding=query_embedding,
            document_ids=request.document_ids,
            top_n=top_n,
        )
    except Exception as exc:
        log.error("Retrieval failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval error: {exc}",
        ) from exc
    retrieval_ms = round((time.monotonic() - retrieval_start) * 1000, 1)

    total_ms = round((time.monotonic() - pipeline_start) * 1000, 1)

    log.info(
        "Query pipeline complete",
        route=route.value,
        candidates=len(candidates),
        embed_ms=embed_ms,
        retrieval_ms=retrieval_ms,
        total_ms=total_ms,
    )

    # ── Build response ────────────────────────────────────────────────────────
    sources = [_candidate_to_source(c) for c in candidates]

    return QueryResponse(
        answer=(
            f"Retrieved {len(candidates)} candidate chunk(s) via '{route.value}' route. "
            "Answer generation not yet available — reranker and LLM will be wired in the next pipeline stage."
        ),
        sources=sources,
        route_type=route,
        cache_hit=False,
        model_used="",
        provider_used="",
        latency=LatencyBreakdown(
            total_ms=total_ms,
            cache_check_ms=0.0,
            query_embed_ms=embed_ms,
            retrieval_ms=retrieval_ms,
            reranking_ms=0.0,
            llm_ms=0.0,
        ),
        token_usage={},
        cost_usd=0.0,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _run_retrieval(
    route: RouteType,
    query_embedding: list,
    document_ids,
    top_n: int,
) -> List[RetrievalResult]:
    """Dispatch to the correct retrieval strategy based on route."""
    if route == RouteType.TEXT:
        return retrieve_text(
            query_embedding=query_embedding,
            document_ids=document_ids,
            top_n=top_n,
        )
    elif route == RouteType.MULTIMODAL:
        return retrieve_multimodal(
            query_embedding=query_embedding,
            document_ids=document_ids,
            top_n=top_n,
        )
    else:  # HYBRID
        return retrieve_hybrid(
            query_embedding=query_embedding,
            document_ids=document_ids,
            top_n=top_n,
        )


def _candidate_to_source(candidate: RetrievalResult) -> Source:
    """Convert a RetrievalResult into a Source (grounding citation)."""
    return Source(
        document_id=candidate.document_id,
        chunk_id=candidate.chunk_id,
        page=candidate.page,
        bbox=candidate.bbox,
        chunk_type=candidate.chunk_type,
        text_preview=candidate.text[:200],
        relevance_score=candidate.similarity_score,
        filename="",  # Populated in Day 5 after document store lookup
    )
