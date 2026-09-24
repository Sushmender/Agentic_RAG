"""
backend/app/services/query_router.py
Deterministic query router for Day 4.

Routes a natural-language query to one of three retrieval strategies:
  - text       → no multimodal keywords detected
  - multimodal → query explicitly targets visual elements (table, chart, figure …)
  - hybrid     → visual keywords present AND query is broad/compound enough to
                  warrant both text and visual candidates

Design decisions:
  - Zero LLM calls — pure heuristic/keyword matching.
  - Hybrid heuristic: multimodal keyword hit + (query is long OR contains
    connective words like "and", "also", "both", "including", "with").
    This catches "Describe the chart and its text caption" without being
    overly aggressive.
  - Case-insensitive; punctuation stripped before matching.
"""
from __future__ import annotations

import re
from typing import FrozenSet

from app.core.logging import get_logger
from app.schemas.query import RouteType

logger = get_logger(__name__)

# ── Trigger keyword sets ───────────────────────────────────────────────────────

MULTIMODAL_KEYWORDS: FrozenSet[str] = frozenset({
    "table", "chart", "figure", "image", "graph", "plot",
    "diagram", "visual", "picture", "scan", "handwritten",
    "layout", "column", "row",
})

# Connective / compound words that signal a hybrid query
HYBRID_CONNECTIVES: FrozenSet[str] = frozenset({
    "and", "also", "both", "including", "with", "as well",
    "along", "besides", "plus", "together",
})

# Minimum word count to consider a query "compound" without an explicit connective
HYBRID_MIN_WORDS: int = 8


# ── Public API ─────────────────────────────────────────────────────────────────

def route_query(query: str) -> RouteType:
    """
    Classify a user query into text / multimodal / hybrid.

    Args:
        query: Raw natural-language question from the user.

    Returns:
        RouteType enum value.
    """
    normalised = _normalise(query)
    tokens = set(normalised.split())
    word_count = len(normalised.split())

    # Keyword hits
    hits = tokens & MULTIMODAL_KEYWORDS
    has_multimodal_keyword = bool(hits)

    if not has_multimodal_keyword:
        route = RouteType.TEXT
    else:
        # Check for hybrid signals: connective words OR long compound query
        has_connective = bool(tokens & HYBRID_CONNECTIVES)
        is_long = word_count >= HYBRID_MIN_WORDS
        if has_connective or is_long:
            route = RouteType.HYBRID
        else:
            route = RouteType.MULTIMODAL

    logger.info(
        "Query routed",
        route=route.value,
        keyword_hits=sorted(hits),
        word_count=word_count,
        query_preview=query[:80],
    )
    return route


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lowercase and strip punctuation for keyword matching."""
    return re.sub(r"[^\w\s]", " ", text.lower())
