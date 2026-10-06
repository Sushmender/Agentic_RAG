"""
backend/evaluation/evaluator.py
RAG evaluation engine — Recall@K, Precision@K, pipeline evaluation.

Metrics:
  Recall@K    = |intersection(retrieved_ids[:K], expected_ids)| / |expected_ids|
  Precision@K = |intersection(retrieved_ids[:K], expected_ids)| / K

evaluate_pipeline():
  For each gold question:
    1. Embed query (OpenRouter embedding provider)
    2. Retrieve Top-N with retrieve_hybrid() → pre-rerank candidates
    3. Compute pre-rerank Recall@K, Precision@K
    4. Rerank Top-K (OpenRouter NVIDIA reranker)
    5. Compute post-rerank Recall@K, Precision@K
  Aggregate: average metrics across all questions.
  Return per-question detail + aggregate summary.

Output schema:
  {
    "k": int,
    "pre_rerank":  { "recall_at_k": float, "precision_at_k": float },
    "post_rerank": { "recall_at_k": float, "precision_at_k": float },
    "per_question": [
      {
        "question": str,
        "expected_chunk_ids": [...],
        "pre_rerank_candidates": [...],
        "post_rerank_candidates": [...],
        "pre_rerank":  { "recall_at_k": float, "precision_at_k": float },
        "post_rerank": { "recall_at_k": float, "precision_at_k": float }
      }
    ]
  }
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.openrouter_embedding import embedding_provider
from app.providers.openrouter_reranker import reranker_provider
from app.services.context_assembly import _clean_text
from app.services.retrieval_service import DEFAULT_TOP_N, retrieve_hybrid

logger = get_logger(__name__)
settings = get_settings()


# ── Metric Functions ───────────────────────────────────────────────────────────

def recall_at_k(
    retrieved_ids: List[str],
    expected_ids: List[str],
    k: int,
) -> float:
    """
    Compute Recall@K.

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs (pre or post rerank).
        expected_ids:  Ground-truth expected chunk IDs.
        k:             Cut-off rank.

    Returns:
        Float in [0, 1]. Returns 0.0 if expected_ids is empty.
    """
    if not expected_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & set(expected_ids))
    return hits / len(expected_ids)


def precision_at_k(
    retrieved_ids: List[str],
    expected_ids: List[str],
    k: int,
) -> float:
    """
    Compute Precision@K.

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs.
        expected_ids:  Ground-truth expected chunk IDs.
        k:             Cut-off rank.

    Returns:
        Float in [0, 1]. Returns 0.0 if k == 0.
    """
    if k == 0:
        return 0.0
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & set(expected_ids))
    return hits / k


# ── Pipeline Evaluator ─────────────────────────────────────────────────────────

async def evaluate_pipeline(
    gold_dataset: List[Dict[str, Any]],
    k: int = 5,
) -> Dict[str, Any]:
    """
    Run full retrieval + reranking evaluation against the gold dataset.

    Args:
        gold_dataset: List of gold entries (question, expected_document_ids,
                      expected_chunk_ids).
        k:            Recall@K / Precision@K cut-off. Default: 5.

    Returns:
        Evaluation report with aggregate and per-question metrics.
    """
    if not gold_dataset:
        logger.warning("Gold dataset is empty — nothing to evaluate")
        return _empty_report(k)

    per_question: List[Dict[str, Any]] = []
    top_n = DEFAULT_TOP_N  # how many candidates to retrieve before reranking

    for entry in gold_dataset:
        question = entry.get("question", "")
        expected_doc_ids: List[str] = entry.get("expected_document_ids", [])
        expected_chunk_ids: List[str] = entry.get("expected_chunk_ids", [])

        log = logger.bind(question_preview=question[:60])

        # ── Step 1: Embed query ────────────────────────────────────────────────
        try:
            query_embedding = await embedding_provider.embed_query(question)
        except Exception as exc:
            log.error("Failed to embed evaluation query", error=str(exc))
            per_question.append(_failed_entry(entry, k, reason=str(exc)))
            continue

        # ── Step 2: Retrieve Top-N candidates (pre-rerank) ────────────────────
        try:
            candidates = retrieve_hybrid(
                query_embedding=query_embedding,
                document_ids=expected_doc_ids or None,
                top_n=top_n,
            )
        except Exception as exc:
            log.error("Retrieval failed for evaluation query", error=str(exc))
            per_question.append(_failed_entry(entry, k, reason=str(exc)))
            continue

        pre_ids = [c.chunk_id for c in candidates]
        pre_recall = recall_at_k(pre_ids, expected_chunk_ids, k)
        pre_prec   = precision_at_k(pre_ids, expected_chunk_ids, k)

        log.debug(
            "Pre-rerank metrics",
            pre_recall_at_k=pre_recall,
            pre_precision_at_k=pre_prec,
            candidates=len(candidates),
        )

        # ── Step 3: Rerank Top-K ───────────────────────────────────────────────
        try:
            candidate_dicts = [
                {
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "chunk_type": c.chunk_type,
                    "page": c.page,
                    "bbox": c.bbox,
                    "text": _clean_text(c.text),
                    "similarity_score": c.similarity_score,
                }
                for c in candidates
            ]
            reranked_dicts = await reranker_provider.rerank(
                query=question,
                candidates=candidate_dicts,
                top_k=k,
            )
            post_ids = [d["chunk_id"] for d in reranked_dicts]
        except Exception as exc:
            log.warning(
                "Reranking failed — using raw retrieval order for post-rerank metrics",
                error=str(exc),
            )
            post_ids = pre_ids[:k]

        post_recall = recall_at_k(post_ids, expected_chunk_ids, k)
        post_prec   = precision_at_k(post_ids, expected_chunk_ids, k)

        log.info(
            "Evaluation question done",
            pre_recall=pre_recall,
            pre_prec=pre_prec,
            post_recall=post_recall,
            post_prec=post_prec,
        )

        per_question.append({
            "question": question,
            "expected_chunk_ids": expected_chunk_ids,
            "pre_rerank_candidate_ids": pre_ids,
            "post_rerank_candidate_ids": post_ids,
            "pre_rerank": {
                "recall_at_k":    round(pre_recall, 4),
                "precision_at_k": round(pre_prec, 4),
            },
            "post_rerank": {
                "recall_at_k":    round(post_recall, 4),
                "precision_at_k": round(post_prec, 4),
            },
        })

    # ── Aggregate ──────────────────────────────────────────────────────────────
    n = len(per_question)
    if n == 0:
        return _empty_report(k)

    agg_pre_recall  = sum(q["pre_rerank"]["recall_at_k"]    for q in per_question) / n
    agg_pre_prec    = sum(q["pre_rerank"]["precision_at_k"] for q in per_question) / n
    agg_post_recall = sum(q["post_rerank"]["recall_at_k"]   for q in per_question) / n
    agg_post_prec   = sum(q["post_rerank"]["precision_at_k"] for q in per_question) / n

    logger.info(
        "Evaluation complete",
        k=k,
        questions_evaluated=n,
        pre_recall_avg=round(agg_pre_recall, 4),
        post_recall_avg=round(agg_post_recall, 4),
    )

    return {
        "k": k,
        "questions_evaluated": n,
        "pre_rerank": {
            "recall_at_k":    round(agg_pre_recall, 4),
            "precision_at_k": round(agg_pre_prec, 4),
        },
        "post_rerank": {
            "recall_at_k":    round(agg_post_recall, 4),
            "precision_at_k": round(agg_post_prec, 4),
        },
        "per_question": per_question,
    }


# ── Internal helpers ───────────────────────────────────────────────────────────

def _empty_report(k: int) -> Dict[str, Any]:
    """Return a zero-valued report when no questions could be evaluated."""
    return {
        "k": k,
        "questions_evaluated": 0,
        "pre_rerank":  {"recall_at_k": 0.0, "precision_at_k": 0.0},
        "post_rerank": {"recall_at_k": 0.0, "precision_at_k": 0.0},
        "per_question": [],
    }


def _failed_entry(entry: Dict[str, Any], k: int, reason: str) -> Dict[str, Any]:
    """Return a zero-metric entry for a question that failed during evaluation."""
    return {
        "question": entry.get("question", ""),
        "expected_chunk_ids": entry.get("expected_chunk_ids", []),
        "pre_rerank_candidate_ids": [],
        "post_rerank_candidate_ids": [],
        "pre_rerank":  {"recall_at_k": 0.0, "precision_at_k": 0.0},
        "post_rerank": {"recall_at_k": 0.0, "precision_at_k": 0.0},
        "error": reason,
    }
