"""
backend/app/api/v1/endpoints/evaluation.py
Evaluation endpoint — GET /evaluation/run

Triggers RAG evaluation on the gold dataset (loaded or auto-generated)
and returns pre/post-rerank Recall@K and Precision@K metrics.

Auth: Open (no JWT required) — admin/debug tooling like /metrics and /health.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.logging import get_logger
from app.evaluation.gold_dataset import load_or_generate
from app.evaluation.evaluator import evaluate_pipeline
from app.db.chromadb_client import get_collection_stats

logger = get_logger(__name__)

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])


@router.get(
    "/run",
    summary="Run RAG evaluation against the gold dataset",
    description=(
        "Loads (or generates) the gold question dataset, then runs the full "
        "retrieval + reranking pipeline for each question and computes "
        "Recall@K and Precision@K before and after reranking. "
        "Returns aggregate and per-question metrics. "
        "No authentication required — this is an admin/observability endpoint."
    ),
)
async def run_evaluation(k: int = 5) -> dict:
    """
    GET /evaluation/run?k=5

    Query params:
        k: Recall@K / Precision@K cut-off (default 5, max 20).

    Returns:
        {
          "k": int,
          "questions_evaluated": int,
          "pre_rerank":  { "recall_at_k": float, "precision_at_k": float },
          "post_rerank": { "recall_at_k": float, "precision_at_k": float },
          "per_question": [ ... ]
        }

    Raises:
        400: No documents are indexed in ChromaDB — cannot evaluate.
    """
    # Guard: require at least one indexed document
    try:
        stats = get_collection_stats()
        if stats.get("total_chunks", 0) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "No documents indexed — cannot evaluate",
                    "hint": "Upload and ingest at least one document before running evaluation.",
                },
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to check ChromaDB stats", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ChromaDB error: {exc}",
        ) from exc

    # Clamp k
    k = max(1, min(k, 20))

    # Load or auto-generate gold dataset
    try:
        gold_dataset = load_or_generate()
    except Exception as exc:
        logger.error("Failed to load/generate gold dataset", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gold dataset error: {exc}",
        ) from exc

    if not gold_dataset:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "No documents indexed — cannot evaluate",
                "hint": "Upload and ingest at least one document, then re-run evaluation.",
            },
        )

    logger.info("Starting evaluation", k=k, gold_questions=len(gold_dataset))

    # Run evaluation
    try:
        report = await evaluate_pipeline(gold_dataset=gold_dataset, k=k)
    except Exception as exc:
        logger.error("Evaluation pipeline failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation error: {exc}",
        ) from exc

    logger.info(
        "Evaluation complete",
        k=k,
        questions=report.get("questions_evaluated", 0),
        pre_recall=report.get("pre_rerank", {}).get("recall_at_k"),
        post_recall=report.get("post_rerank", {}).get("recall_at_k"),
    )

    return report
