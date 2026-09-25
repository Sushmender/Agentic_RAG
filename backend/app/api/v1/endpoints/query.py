"""
backend/app/api/v1/endpoints/query.py
Query endpoint — complete multimodal RAG pipeline (Day 5).

Full pipeline:
  Route → Embed query → Retrieve Top-N → Rerank Top-K → Assemble context
  → Generate grounded answer → Return QueryResponse

Reranker failure handling:
  If the reranker fails, we log the error and fall back to raw retrieval
  order (unranked Top-N → assemble context → still generate an answer).

Day 6: Redis cache check before pipeline.
"""
from __future__ import annotations

import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import get_current_user_id
from app.db.in_memory_store import document_store
from app.providers.openrouter_embedding import embedding_provider
from app.providers.openrouter_reranker import reranker_provider
from app.schemas.query import (
    LatencyBreakdown,
    QueryRequest,
    QueryResponse,
    RetrievalResult,
    RouteType,
    Source,
)
from app.services.context_assembly import assemble_context, _clean_text
from app.services.llm_service import generate_answer
from app.services.query_router import route_query
from app.services.retrieval_service import (
    DEFAULT_TOP_N,
    retrieve_hybrid,
    retrieve_multimodal,
    retrieve_text,
)

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/query", tags=["Query"])


@router.post(
    "",
    response_model=QueryResponse,
    summary="Ask a question about ingested documents",
    description=(
        "Full multimodal RAG pipeline: "
        "route → embed → retrieve → rerank → assemble context → generate. "
        "Returns a grounded answer with source citations and latency breakdown. "
        "Checks Redis cache first (Day 6)."
    ),
)
async def query(
    request: QueryRequest,
    user_id: str = Depends(get_current_user_id),
) -> QueryResponse:
    """
    Complete Day 5 pipeline:
      1. Classify query → RouteType
      2. Embed query (query mode)
      3. Retrieve Top-N candidates (ChromaDB cosine similarity)
      4. Rerank Top-K via OpenRouter Nemotron reranker
         → on failure: log error, use raw retrieval order
      5. Assemble grounded context (token-budgeted, [Source N] citations)
      6. Generate answer via Groq (primary) or OpenRouter (fallback/user-choice)
      7. Return QueryResponse with answer + sources + latency
    """
    pipeline_start = time.monotonic()
    cfg = get_settings()
    top_n = DEFAULT_TOP_N
    top_k = request.top_k or cfg.RERANK_TOP_K
    preferred_provider = (request.llm_provider or "groq").lower()

    log = logger.bind(
        user_id=user_id,
        query_preview=request.query[:80],
        preferred_provider=preferred_provider,
        top_n=top_n,
        top_k=top_k,
    )
    if request.document_ids:
        log = log.bind(document_ids=request.document_ids)

    log.info("Query pipeline started")

    # ── Step 1: Route ─────────────────────────────────────────────────────────
    route = route_query(request.query)
    log.info("Query routed", route=route.value)

    # ── Step 2: Embed query ───────────────────────────────────────────────────
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
    log.info("Query embedded", embed_ms=embed_ms)

    # ── Step 3: Retrieve Top-N ────────────────────────────────────────────────
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
    log.info("Retrieval complete", candidates=len(candidates), retrieval_ms=retrieval_ms)

    if not candidates:
        # No chunks found — return early with informative message
        total_ms = round((time.monotonic() - pipeline_start) * 1000, 1)
        return QueryResponse(
            answer=(
                "No relevant content found in the indexed documents for your query. "
                "Please try rephrasing your question or upload more documents."
            ),
            sources=[],
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

    # ── Step 4: Rerank Top-K ──────────────────────────────────────────────────
    rerank_start = time.monotonic()
    reranked_candidates: List[RetrievalResult]
    rerank_skipped = False

    try:
        # Convert RetrievalResult to dicts for the reranker.
        # Strip HTML from text so the reranker scores actual content.
        candidate_dicts = [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "chunk_type": c.chunk_type,
                "page": c.page,
                "bbox": c.bbox,
                "text": _clean_text(c.text),   # <-- clean for reranker
                "similarity_score": c.similarity_score,
            }
            for c in candidates
        ]


        reranked_dicts = await reranker_provider.rerank(
            query=request.query,
            candidates=candidate_dicts,
            top_k=top_k,
        )

        # Convert reranked dicts back to RetrievalResult (with updated scores)
        reranked_candidates = [
            RetrievalResult(
                chunk_id=d["chunk_id"],
                document_id=d["document_id"],
                chunk_type=d["chunk_type"],
                page=d["page"],
                bbox=d["bbox"],
                text=d["text"],
                similarity_score=d.get("relevance_score", d.get("similarity_score", 0.0)),
            )
            for d in reranked_dicts
        ]
        log.info(
            "Reranking complete",
            before=len(candidates),
            after=len(reranked_candidates),
        )

    except Exception as exc:
        # Reranker failure: log, skip reranking, use raw retrieval order
        log.error(
            "Reranker failed — skipping reranking, using raw retrieval order",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        # Fall back to raw retrieval, limit to top_k
        reranked_candidates = candidates[:top_k]
        rerank_skipped = True

    rerank_ms = round((time.monotonic() - rerank_start) * 1000, 1)

    # ── Step 5: Assemble grounded context ─────────────────────────────────────
    assembled = assemble_context(
        candidates=reranked_candidates,
        query=request.query,
        top_k=top_k,
        max_tokens=cfg.MAX_CONTEXT_TOKENS,
    )
    log.info(
        "Context assembled",
        chunks_selected=len(assembled.selected_chunks),
        tokens_est=assembled.total_tokens_est,
        truncated=assembled.chunks_truncated,
    )

    # ── Step 6: Generate answer ───────────────────────────────────────────────
    llm_start = time.monotonic()
    try:
        llm_result = await generate_answer(
            assembled=assembled,
            query=request.query,
            preferred_provider=preferred_provider,
            max_tokens=1024,
        )
    except Exception as exc:
        log.error("LLM generation failed (both providers)", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM generation failed: {exc}",
        ) from exc
    llm_ms = round((time.monotonic() - llm_start) * 1000, 1)

    total_ms = round((time.monotonic() - pipeline_start) * 1000, 1)

    log.info(
        "Query pipeline complete",
        route=route.value,
        provider=llm_result.provider_used,
        model=llm_result.model_used,
        fallback=llm_result.fallback_triggered,
        rerank_skipped=rerank_skipped,
        total_ms=total_ms,
        llm_ms=llm_ms,
        total_tokens=llm_result.total_tokens,
        cost_usd=llm_result.cost_usd,
    )

    # ── Build sources (from selected chunks after context assembly) ────────────
    sources = [
        _chunk_to_source(chunk, rank=i + 1)
        for i, chunk in enumerate(assembled.selected_chunks)
    ]

    return QueryResponse(
        answer=llm_result.answer,
        sources=sources,
        route_type=route,
        cache_hit=False,
        model_used=llm_result.model_used,
        provider_used=llm_result.provider_used,
        latency=LatencyBreakdown(
            total_ms=total_ms,
            cache_check_ms=0.0,
            query_embed_ms=embed_ms,
            retrieval_ms=retrieval_ms,
            reranking_ms=rerank_ms,
            llm_ms=llm_ms,
        ),
        token_usage={
            "input_tokens": llm_result.input_tokens,
            "output_tokens": llm_result.output_tokens,
            "total_tokens": llm_result.total_tokens,
        },
        cost_usd=llm_result.cost_usd,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _run_retrieval(
    route: RouteType,
    query_embedding: list,
    document_ids: Optional[List[str]],
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


def _chunk_to_source(chunk: RetrievalResult, rank: int) -> Source:
    """Convert a RetrievalResult (post-rerank) into a Source citation."""
    # Resolve filename from document store
    filename = ""
    try:
        doc = document_store.get(chunk.document_id)
        if doc:
            filename = doc.filename
    except Exception:
        pass  # Non-critical — filename is display-only

    # Strip HTML artefacts from preview (ADE stores table HTML in chunk text)
    clean_preview = _clean_text(chunk.text) if chunk.text else ""

    return Source(
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        page=chunk.page,
        bbox=chunk.bbox,
        chunk_type=chunk.chunk_type,
        text_preview=clean_preview,
        relevance_score=chunk.similarity_score,
        filename=filename,
    )
