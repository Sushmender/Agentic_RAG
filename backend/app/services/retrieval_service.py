"""
backend/app/services/retrieval_service.py
Retrieval strategies for Day 4 — text, multimodal, hybrid.

All three strategies delegate to chromadb_client.query_similar() and return
List[RetrievalResult].  No LLM calls are made here; reranking is Day 5.

Strategy details
────────────────
retrieve_text()
  • ChromaDB query with no chunk_type filter (all types allowed).
  • Caller intent: user asked a plain text question — text chunks dominate
    by cosine score, but we don't hard-exclude tables/figures in case a
    table happens to be the most relevant match.

retrieve_multimodal()
  • Same as retrieve_text() — no filter (option A confirmed by user).
  • All chunk types compete on similarity.  The reranker (Day 5) will
    surface the most relevant ones regardless of modality.

retrieve_hybrid()
  • Runs TWO separate ChromaDB queries (option A confirmed by user):
      1. text-only filter  → top_n candidates
      2. non-text filter   → top_n candidates
  • Merges both sets, deduplicates by chunk_id, re-sorts by similarity_score
    descending, returns the best top_n.
  • This guarantees both modalities are represented in the candidate pool
    before reranking.

Document scoping
────────────────
When document_ids is provided, a ChromaDB `where` filter is applied:
  • 1 doc  → {"document_id": {"$eq": doc_id}}
  • N docs → {"document_id": {"$in": [...]}}
This is OR-combined with any chunk_type filter using {"$and": [...]}.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.db.chromadb_client import query_similar
from app.schemas.query import RetrievalResult

logger = get_logger(__name__)

DEFAULT_TOP_N: int = 20


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve_text(
    query_embedding: List[float],
    document_ids: Optional[List[str]] = None,
    top_n: int = DEFAULT_TOP_N,
) -> List[RetrievalResult]:
    """
    Retrieve top-N candidates using cosine similarity with no chunk_type filter.
    All chunk types (text, table, figure) compete equally on similarity score.

    Args:
        query_embedding: 1-D embedding vector for the user query (query mode).
        document_ids:    Optional list of document IDs to scope the search.
        top_n:           Maximum number of candidates to return.

    Returns:
        List of RetrievalResult sorted by similarity_score descending.
    """
    t0 = time.monotonic()
    where = _build_where(document_ids=document_ids, chunk_type_filter=None)
    raw = query_similar(embedding=query_embedding, n_results=top_n, where=where)
    results = [_to_retrieval_result(r) for r in raw]
    _log("text", results, t0)
    return results


def retrieve_multimodal(
    query_embedding: List[float],
    document_ids: Optional[List[str]] = None,
    top_n: int = DEFAULT_TOP_N,
) -> List[RetrievalResult]:
    """
    Retrieve top-N candidates with no chunk_type filter (all types).
    Identical logic to retrieve_text; separated by name for clarity and
    future flexibility (e.g. multimodal-specific re-scoring in Day 5).

    Args:
        query_embedding: 1-D embedding vector for the user query (query mode).
        document_ids:    Optional list of document IDs to scope the search.
        top_n:           Maximum number of candidates to return.

    Returns:
        List of RetrievalResult sorted by similarity_score descending.
    """
    t0 = time.monotonic()
    where = _build_where(document_ids=document_ids, chunk_type_filter=None)
    raw = query_similar(embedding=query_embedding, n_results=top_n, where=where)
    results = [_to_retrieval_result(r) for r in raw]
    _log("multimodal", results, t0)
    return results


def retrieve_hybrid(
    query_embedding: List[float],
    document_ids: Optional[List[str]] = None,
    top_n: int = DEFAULT_TOP_N,
) -> List[RetrievalResult]:
    """
    Retrieve top-N candidates by running TWO ChromaDB queries and merging.

    Query 1 — text-only filter   (chunk_type = "text")
    Query 2 — non-text filter    (chunk_type IN ["table", "figure"])

    Results are deduplicated by chunk_id and re-ranked by similarity_score
    before returning the best top_n.

    Args:
        query_embedding: 1-D embedding vector for the user query (query mode).
        document_ids:    Optional list of document IDs to scope the search.
        top_n:           Maximum number of candidates to return after merge.

    Returns:
        Merged, deduplicated List[RetrievalResult] sorted by similarity_score desc.
    """
    t0 = time.monotonic()

    # Query 1: text chunks
    where_text = _build_where(
        document_ids=document_ids,
        chunk_type_filter={"chunk_type": {"$eq": "text"}},
    )
    raw_text = query_similar(embedding=query_embedding, n_results=top_n, where=where_text)

    # Query 2: visual chunks (table + figure)
    where_visual = _build_where(
        document_ids=document_ids,
        chunk_type_filter={"chunk_type": {"$in": ["table", "figure"]}},
    )
    raw_visual = query_similar(embedding=query_embedding, n_results=top_n, where=where_visual)

    # Merge + deduplicate + re-sort
    seen: set[str] = set()
    merged: List[RetrievalResult] = []
    for r in raw_text + raw_visual:
        item = _to_retrieval_result(r)
        if item.chunk_id not in seen:
            seen.add(item.chunk_id)
            merged.append(item)

    merged.sort(key=lambda x: x.similarity_score, reverse=True)
    results = merged[:top_n]

    _log("hybrid", results, t0, extra={"text_raw": len(raw_text), "visual_raw": len(raw_visual)})
    return results


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_where(
    document_ids: Optional[List[str]],
    chunk_type_filter: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Compose a ChromaDB `where` dict from optional document_ids scope
    and an optional chunk_type filter clause.

    ChromaDB compound filter syntax: {"$and": [clause1, clause2]}
    """
    clauses: List[Dict[str, Any]] = []

    if document_ids:
        if len(document_ids) == 1:
            clauses.append({"document_id": {"$eq": document_ids[0]}})
        else:
            clauses.append({"document_id": {"$in": document_ids}})

    if chunk_type_filter:
        clauses.append(chunk_type_filter)

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _to_retrieval_result(raw: Dict[str, Any]) -> RetrievalResult:
    """Convert a raw chromadb_client result dict into a typed RetrievalResult."""
    return RetrievalResult(
        chunk_id=raw["chunk_id"],
        document_id=raw["document_id"],
        chunk_type=raw["chunk_type"],
        page=raw["page"],
        bbox=raw["bbox"],
        text=raw["text"],
        similarity_score=raw["similarity_score"],
    )


def _log(
    strategy: str,
    results: List[RetrievalResult],
    t0: float,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    log_data: Dict[str, Any] = {
        "strategy": strategy,
        "results_count": len(results),
        "latency_ms": latency_ms,
    }
    if extra:
        log_data.update(extra)
    logger.info("Retrieval complete", **log_data)
