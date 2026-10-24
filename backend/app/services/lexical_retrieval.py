"""
backend/app/services/lexical_retrieval.py
BM25-based lexical fallback retrieval -- used when embedding fails.

Design:
  - Pure Python, no new dependencies (math/re/string from stdlib only).
  - Lowercase, strip punctuation, remove common English stop words.
  - BM25 scoring: k1=1.5, b=0.75.
  - Scoping guarantee: only chunks from retrieval_doc_ids are considered,
    identical to the vector retrieval scoping, so a caller can NEVER get
    another user's chunks through the fallback path.

Public API:
  lexical_retrieve(query, document_ids, top_n) -> List[RetrievalResult]
"""
from __future__ import annotations

import math
import re
import string
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.db.chromadb_client import get_collection
from app.schemas.query import RetrievalResult

logger = get_logger(__name__)

# BM25 hyperparameters
_K1: float = 1.5
_B: float  = 0.75

# Common English stop words (minimal set, pure Python)
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "not", "no", "nor",
    "so", "yet", "both", "either", "neither", "this", "that", "these",
    "those", "it", "its", "i", "me", "my", "we", "our", "you", "your",
    "he", "she", "they", "them", "their", "what", "which", "who", "how",
    "when", "where", "why", "all", "any", "each", "few", "more", "most",
    "other", "such", "than", "too", "very", "just", "as", "if", "then",
    "there", "about", "into", "up", "out", "over", "after", "before",
})

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def _tokenize(text: str) -> List[str]:
    """Lowercase, strip punctuation, split, remove stop words."""
    cleaned = text.lower().translate(_PUNCT_TABLE)
    tokens  = [t for t in cleaned.split() if t and t not in _STOP_WORDS]
    return tokens


def _bm25_score(
    query_tokens: List[str],
    doc_tokens: List[str],
    avg_dl: float,
    df: Dict[str, int],
    n_docs: int,
) -> float:
    """Compute BM25 score for a single document."""
    dl = len(doc_tokens)
    freq: Dict[str, int] = {}
    for t in doc_tokens:
        freq[t] = freq.get(t, 0) + 1

    score = 0.0
    for term in query_tokens:
        if term not in freq:
            continue
        tf  = freq[term]
        idf = math.log(1 + (n_docs - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
        tf_norm = (tf * (_K1 + 1)) / (tf + _K1 * (1 - _B + _B * dl / max(avg_dl, 1)))
        score += idf * tf_norm

    return score


def _get_chunks_for_docs(document_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch all chunks for the given document IDs from ChromaDB using .get()
    (no embedding required).  Returns at most MAX_CHUNKS chunks.
    Scoping guarantee: only chunks whose document_id is in document_ids.
    """
    MAX_CHUNKS = 500   # safety cap
    collection = get_collection()

    if len(document_ids) == 1:
        where: Dict[str, Any] = {"document_id": {"$eq": document_ids[0]}}
    else:
        where = {"document_id": {"$in": document_ids}}

    result = collection.get(
        where=where,
        include=["documents", "metadatas"],
        limit=MAX_CHUNKS,
    )

    ids_list    = result.get("ids") or []
    metas_list  = result.get("metadatas") or []
    docs_list   = result.get("documents") or []

    chunks: List[Dict[str, Any]] = []
    for chunk_id, meta, doc in zip(ids_list, metas_list, docs_list):
        if not meta or not doc:
            continue
        bbox = [
            float(meta.get("bbox_x0", 0.0)),
            float(meta.get("bbox_y0", 0.0)),
            float(meta.get("bbox_x1", 0.0)),
            float(meta.get("bbox_y1", 0.0)),
        ]
        chunks.append({
            "chunk_id":    chunk_id,
            "document_id": meta.get("document_id", ""),
            "chunk_type":  meta.get("chunk_type", "text"),
            "page":        int(meta.get("page", 0)),
            "bbox":        bbox,
            "text":        doc,
        })
    return chunks


def lexical_retrieve(
    query: str,
    document_ids: List[str],
    top_n: int = 20,
) -> List[RetrievalResult]:
    """
    Retrieve up to top_n chunks from the specified documents using BM25.

    If the total number of chunks across the specified documents is <= 40,
    all chunks are returned (no scoring needed).  Otherwise BM25 scores
    the chunks and returns the top_n by relevance.

    Scoping is identical to vector retrieval: only document_ids are searched.

    Returns:
        List[RetrievalResult] sorted by BM25 score descending.
        similarity_score field contains the BM25 score (may be 0.0 for all
        if query tokens do not appear in any chunk).
    """
    if not document_ids:
        logger.warning("lexical_retrieve called with empty document_ids -- returning []")
        return []

    chunks = _get_chunks_for_docs(document_ids)
    if not chunks:
        logger.info("lexical_retrieve: no chunks found for document_ids", doc_count=len(document_ids))
        return []

    logger.info(
        "lexical_retrieve: fetched chunks",
        total_chunks=len(chunks),
        doc_ids=document_ids,
        top_n=top_n,
    )

    # If small enough, return all (no scoring)
    if len(chunks) <= 40:
        results = [
            RetrievalResult(
                chunk_id=c["chunk_id"],
                document_id=c["document_id"],
                chunk_type=c["chunk_type"],
                page=c["page"],
                bbox=c["bbox"],
                text=c["text"],
                similarity_score=1.0,   # equal weight when returning all
            )
            for c in chunks
        ]
        logger.info("lexical_retrieve: small doc set, returning all chunks", count=len(results))
        return results[:top_n]

    # BM25 over all chunks
    query_tokens  = _tokenize(query)
    doc_tokens_list = [_tokenize(c["text"]) for c in chunks]
    n_docs  = len(chunks)
    avg_dl  = sum(len(t) for t in doc_tokens_list) / max(n_docs, 1)

    # Build document frequency table
    df: Dict[str, int] = {}
    for tokens in doc_tokens_list:
        seen = set(tokens)
        for t in seen:
            df[t] = df.get(t, 0) + 1

    scored: List[tuple[float, Dict[str, Any]]] = []
    for chunk, tokens in zip(chunks, doc_tokens_list):
        score = _bm25_score(query_tokens, tokens, avg_dl, df, n_docs)
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_n]

    results = [
        RetrievalResult(
            chunk_id=c["chunk_id"],
            document_id=c["document_id"],
            chunk_type=c["chunk_type"],
            page=c["page"],
            bbox=c["bbox"],
            text=c["text"],
            similarity_score=round(score, 6),
        )
        for score, c in top
    ]

    logger.info(
        "lexical_retrieve: BM25 complete",
        returned=len(results),
        top_score=round(top[0][0], 4) if top else 0,
    )
    return results
