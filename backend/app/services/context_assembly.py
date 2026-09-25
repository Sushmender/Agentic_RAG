"""
backend/app/services/context_assembly.py
Context assembly for the RAG pipeline — Day 5.

Responsibilities:
  1. Select Top-K chunks from a reranked list (already sorted by relevance desc).
  2. Deduplicate by chunk_id (defensive — reranker shouldn't produce duplicates).
  3. Enforce LLM context window: rough token budget via len(text)//4.
  4. Build a grounded prompt string with [Source N] citation tags.
  5. Flag visual chunks (table/figure) with a special annotation.

Token budget note:
  We use len(text) // 4 as a rough token estimate (average English word ≈ 4 chars,
  ≈ 1 token). This avoids pulling in tiktoken as a dependency and is accurate
  enough to prevent context overflow for typical document chunks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.query import RetrievalResult

logger = get_logger(__name__)

# ── HTML cleaning ──────────────────────────────────────────────────────────────
_TAG_RE    = re.compile(r'<[^>]+>')
_MULTI_WS  = re.compile(r'[ \t]{2,}')
_MULTI_NL  = re.compile(r'\n{3,}')
_TABLE_RE  = re.compile(r'<table[^>]*>(.*?)</table>', re.IGNORECASE | re.DOTALL)
_ROW_RE    = re.compile(r'<tr[^>]*>(.*?)</tr>',      re.IGNORECASE | re.DOTALL)
_CELL_RE   = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.IGNORECASE | re.DOTALL)


def _cells_from_row(row_html: str) -> list[str]:
    """Extract clean cell text from a single <tr>...</tr> block."""
    return [
        _TAG_RE.sub('', cell).strip()
        for cell in _CELL_RE.findall(row_html)
    ]


def _html_table_to_markdown(table_html: str) -> str:
    """
    Convert an HTML <table> block to a readable markdown table.

    Example output:
        | Department | Budget ($K) | Actual Spend ($K) | Variance |
        |---|---|---|---|
        | Engineering | 480 | 512 | +32 |
        | Marketing   | 220 | 195 | -25 |
    """
    rows = [_cells_from_row(r) for r in _ROW_RE.findall(table_html)]
    # Drop empty rows
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return ""

    # Pad all rows to the same column count
    max_cols = max(len(r) for r in rows)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]

    def md_row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    lines = [md_row(rows[0])]
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    for row in rows[1:]:
        lines.append(md_row(row))

    return "\n".join(lines)


def _clean_text(raw: str) -> str:
    """
    Clean ADE chunk text for display and LLM consumption.

    - HTML <table> blocks → converted to readable markdown tables
    - All other HTML tags → stripped
    - Redundant whitespace → collapsed

    The original raw text on the chunk object is NEVER modified.
    This function is called at read-time only (context assembly,
    source preview, reranker input).
    """
    # 1. Convert any HTML table blocks to markdown first
    def replace_table(m: re.Match) -> str:
        return "\n" + _html_table_to_markdown(m.group(0)) + "\n"

    text = _TABLE_RE.sub(replace_table, raw)

    # 2. Strip remaining HTML tags (anchors, inline tags, etc.)
    text = _TAG_RE.sub(' ', text)

    # 3. Normalise whitespace
    text = _MULTI_WS.sub(' ', text)
    text = _MULTI_NL.sub('\n\n', text)
    return text.strip()


# ── System prompt template ─────────────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "You are a precise document assistant. "
    "Answer ONLY using the provided evidence below. "
    "Cite sources using [Source N] notation. "
    "If the answer cannot be found in the evidence, say so explicitly. "
    "Do NOT speculate or add information beyond the provided context."
)

_EVIDENCE_HEADER = "EVIDENCE:\n"
_QUESTION_LABEL = "\nQUESTION: "
_ANSWER_LABEL = "\n\nANSWER:"


@dataclass
class AssembledContext:
    """Result of the context assembly step."""
    context_prompt: str          # Full user prompt to send to LLM (evidence + question)
    system_prompt: str           # System instruction for the LLM
    selected_chunks: List[RetrievalResult]  # The Top-K chunks selected
    total_tokens_est: int        # Rough token estimate for the assembled context
    chunks_truncated: bool = False  # True if some chunks were dropped due to token budget


def assemble_context(
    candidates: List[RetrievalResult],
    query: str,
    top_k: int | None = None,
    max_tokens: int | None = None,
) -> AssembledContext:
    """
    Assemble Top-K retrieved/reranked chunks into a grounded LLM prompt.

    Args:
        candidates:  List of RetrievalResult — expected to be sorted by
                     relevance_score descending (reranker output).
        query:       The original user question.
        top_k:       Max chunks to include (defaults to settings.RERANK_TOP_K).
        max_tokens:  Max token budget for the evidence block
                     (defaults to settings.MAX_CONTEXT_TOKENS).

    Returns:
        AssembledContext with the full prompt and selected chunk list.
    """
    cfg = get_settings()
    top_k = top_k or cfg.RERANK_TOP_K
    max_tokens = max_tokens or cfg.MAX_CONTEXT_TOKENS

    log = logger.bind(
        candidates_in=len(candidates),
        top_k=top_k,
        max_tokens=max_tokens,
        query_preview=query[:80],
    )

    # ── Step 1: Deduplicate by chunk_id ──────────────────────────────────────
    seen_ids: set[str] = set()
    unique: List[RetrievalResult] = []
    for chunk in candidates:
        if chunk.chunk_id not in seen_ids:
            seen_ids.add(chunk.chunk_id)
            unique.append(chunk)

    if len(unique) < len(candidates):
        log.warning(
            "Duplicate chunks removed during context assembly",
            removed=len(candidates) - len(unique),
        )

    # ── Step 2: Token-budget enforcement ──────────────────────────────────────
    # Reserve ~500 tokens for question + answer preamble
    available_tokens = max_tokens - 500
    selected: List[RetrievalResult] = []
    tokens_used = 0
    truncated = False

    for chunk in unique[:top_k]:  # Already sorted best-first
        clean = _clean_text(chunk.text)
        chunk_tokens = max(1, len(clean) // 4)
        if tokens_used + chunk_tokens > available_tokens:
            log.warning(
                "Token budget exceeded — dropping remaining chunks",
                chunks_selected=len(selected),
                chunks_dropped=top_k - len(selected),
                tokens_used=tokens_used,
            )
            truncated = True
            break
        selected.append(chunk)
        tokens_used += chunk_tokens

    if not selected and unique:
        # At minimum, include the top chunk truncated to fit
        top_chunk = unique[0]
        max_chars = available_tokens * 4
        truncated_text = top_chunk.text[:max_chars]
        # Create a shallow copy with truncated text
        selected = [
            RetrievalResult(
                chunk_id=top_chunk.chunk_id,
                document_id=top_chunk.document_id,
                chunk_type=top_chunk.chunk_type,
                page=top_chunk.page,
                bbox=top_chunk.bbox,
                text=truncated_text,
                similarity_score=top_chunk.similarity_score,
            )
        ]
        tokens_used = len(truncated_text) // 4
        truncated = True

    log.info(
        "Context assembly complete",
        chunks_selected=len(selected),
        tokens_est=tokens_used,
        truncated=truncated,
    )

    # ── Step 3: Build evidence block ──────────────────────────────────────────
    evidence_parts: List[str] = [_EVIDENCE_HEADER]

    for i, chunk in enumerate(selected, start=1):
        chunk_type = chunk.chunk_type.lower()
        page_label = f"page {chunk.page + 1}"  # 1-indexed for humans

        if chunk_type in ("table", "figure"):
            header = f"[Source {i} — {page_label}, type: {chunk_type}] ⚠️ Visual content"
        else:
            header = f"[Source {i} — {page_label}, type: {chunk_type}]"

        evidence_parts.append(f"{header}\n{_clean_text(chunk.text)}\n")

    evidence_block = "\n".join(evidence_parts)

    # ── Step 4: Compose full prompt ───────────────────────────────────────────
    full_prompt = (
        evidence_block
        + _QUESTION_LABEL
        + query.strip()
        + _ANSWER_LABEL
    )

    # Add question tokens to estimate
    total_tokens_est = tokens_used + len(query) // 4 + 150  # 150 for headers/labels

    return AssembledContext(
        context_prompt=full_prompt,
        system_prompt=_SYSTEM_PROMPT,
        selected_chunks=selected,
        total_tokens_est=total_tokens_est,
        chunks_truncated=truncated,
    )
