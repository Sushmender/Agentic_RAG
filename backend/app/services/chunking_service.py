"""
backend/app/services/chunking_service.py
Normalizes raw LandingAI ADE output into the production Chunk schema.

ADE response shape (confirmed from sample):
  {
    "chunks": [
      {
        "id": "<uuid>",
        "type": "text" | "table" | "figure",
        "markdown": "<full markdown/html content>",
        "grounding": {
          "box": { "left": 0-1, "top": 0-1, "right": 0-1, "bottom": 0-1 },
          "page": 0
        }
      }
    ],
    "markdown": "<full document markdown>",
    "metadata": {
      "credit_usage": 3.0,
      "version": "dpt-2-20260410",
      "page_count": 1,
      "filename": "...",
      ...
    },
    "grounding": {
      "<chunk-id>": {
        "box": { ... },
        "page": 0,
        "type": "chunkText" | "chunkTable" | "chunkFigure",
        "confidence": 0.0-1.0 | null,
        ...
      }
    }
  }

Key decisions:
- chunk_id = SHA-256(document_id + str(page) + str(bbox_rounded) + chunk_type)
  so same content always maps to same ID across re-ingestions.
- bbox format: [x0, y0, x1, y1] = [left, top, right, bottom] normalized 0-1
- Preserve ADE's original markdown in `text` (HTML tables, figure chart syntax)
- Confidence and ADE chunk UUID stored in extra_metadata for future UI use
- Empty/whitespace-only chunks filtered out
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from app.core.logging import get_logger
from app.schemas.chunk import Chunk, ChunkType

logger = get_logger(__name__)

# ── ADE type string → ChunkType enum ──────────────────────────────────────────
_ADE_TYPE_MAP: dict[str, ChunkType] = {
    "text": ChunkType.TEXT,
    "table": ChunkType.TABLE,
    "figure": ChunkType.FIGURE,
    # grounding-level type strings (for future use / cross-reference)
    "chunktext": ChunkType.TEXT,
    "chunktable": ChunkType.TABLE,
    "chunkfigure": ChunkType.FIGURE,
}


def _map_chunk_type(raw_type: str | None) -> ChunkType:
    """Map ADE type string to ChunkType enum, defaulting to UNKNOWN."""
    if raw_type is None:
        return ChunkType.UNKNOWN
    return _ADE_TYPE_MAP.get(raw_type.lower().strip(), ChunkType.UNKNOWN)


def _extract_bbox(grounding_box: dict[str, Any] | None) -> list[float]:
    """
    Convert ADE grounding box {left, top, right, bottom} to [x0, y0, x1, y1].
    Returns [0.0, 0.0, 0.0, 0.0] if missing/invalid.
    """
    if not grounding_box:
        return [0.0, 0.0, 0.0, 0.0]
    try:
        return [
            float(grounding_box.get("left", 0.0)),
            float(grounding_box.get("top", 0.0)),
            float(grounding_box.get("right", 0.0)),
            float(grounding_box.get("bottom", 0.0)),
        ]
    except (TypeError, ValueError):
        return [0.0, 0.0, 0.0, 0.0]


def _stable_chunk_id(
    document_id: str,
    page: int,
    bbox: list[float],
    chunk_type: ChunkType,
) -> str:
    """
    Generate a stable, deterministic chunk_id.
    SHA-256(document_id + page + bbox_rounded_4dp + chunk_type)
    Rounding bbox to 4 decimal places prevents float precision drift
    from producing different IDs for the same chunk across re-ingestions.
    """
    bbox_str = str([round(v, 4) for v in bbox])
    raw = f"{document_id}|{page}|{bbox_str}|{chunk_type}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _clean_anchor_prefix(text: str) -> str:
    """
    ADE prepends an HTML anchor tag to each chunk's markdown.
    e.g.  <a id='b5b4...'></a>\n\nActual content
    We keep the FULL text (as the user wants everything preserved)
    but strip leading whitespace so the content is clean.
    Note: we intentionally do NOT strip the anchor — it links
    back to ADE's grounding map and is useful for future UI features.
    """
    return text.strip()


def normalize_chunks(
    ade_result: dict[str, Any],
    *,
    document_id: str,
    source: str,
) -> list[Chunk]:
    """
    Normalize a raw ADE API response dict into a list of production Chunk objects.

    Args:
        ade_result:   The full JSON response dict from ADE (parsed).
        document_id:  The SHA-256 document ID assigned at upload time.
        source:       Original filename (stored as chunk.source).

    Returns:
        List of normalized Chunk objects (empty/whitespace chunks excluded).
    """
    raw_chunks: list[dict[str, Any]] = ade_result.get("chunks", [])
    metadata: dict[str, Any] = ade_result.get("metadata", {})
    grounding_map: dict[str, Any] = ade_result.get("grounding", {})

    parser_version: str = metadata.get("version", "unknown")
    page_count: int = metadata.get("page_count", 1)

    log = logger.bind(document_id=document_id, source=source, parser_version=parser_version)
    log.info(
        "Normalizing ADE chunks",
        raw_chunk_count=len(raw_chunks),
        page_count=page_count,
    )

    normalized: list[Chunk] = []
    skipped = 0

    for raw in raw_chunks:
        # ── Extract fields from ADE chunk ─────────────────────────────────────
        ade_chunk_id: str = raw.get("id", "")
        raw_type: str = raw.get("type", "")
        markdown_text: str = raw.get("markdown", "")

        # ── Grounding (bbox + page) ───────────────────────────────────────────
        grounding = raw.get("grounding", {})
        box = grounding.get("box", {})
        page: int = int(grounding.get("page", 0))
        bbox: list[float] = _extract_bbox(box)

        # Supplement with top-level grounding map if chunk-level is missing
        if not box and ade_chunk_id in grounding_map:
            top_grounding = grounding_map[ade_chunk_id]
            bbox = _extract_bbox(top_grounding.get("box", {}))
            if not page:
                page = int(top_grounding.get("page", 0))

        # ── Confidence (from grounding map) ───────────────────────────────────
        confidence: float | None = None
        if ade_chunk_id in grounding_map:
            confidence = grounding_map[ade_chunk_id].get("confidence")

        # ── Map chunk type ────────────────────────────────────────────────────
        chunk_type = _map_chunk_type(raw_type)

        # ── Clean text content ────────────────────────────────────────────────
        text = _clean_anchor_prefix(markdown_text)

        # ── Filter empty / whitespace-only chunks ─────────────────────────────
        # Strip HTML tags for whitespace check but keep original text
        text_for_check = re.sub(r"<[^>]+>", "", text).strip()
        if not text_for_check:
            log.debug("Skipping empty chunk", ade_chunk_id=ade_chunk_id, chunk_type=raw_type)
            skipped += 1
            continue

        # ── Generate stable chunk_id ──────────────────────────────────────────
        chunk_id = _stable_chunk_id(document_id, page, bbox, chunk_type)

        # ── Build Chunk object ────────────────────────────────────────────────
        chunk = Chunk(
            chunk_id=chunk_id,
            document_id=document_id,
            chunk_type=chunk_type,
            text=text,                  # full ADE markdown preserved (HTML tables, chart syntax, etc.)
            page=page,
            bbox=bbox,
            source=source,
            parser_version=parser_version,
            # Store ADE's own UUID + confidence so the UI can cross-reference
            # the grounding map in the future (page-level bounding box highlight)
            ade_chunk_id=ade_chunk_id,
            confidence=confidence,
        )
        normalized.append(chunk)

    log.info(
        "Chunk normalization complete",
        total_normalized=len(normalized),
        skipped_empty=skipped,
    )
    return normalized


def parse_ade_metadata(ade_result: dict[str, Any]) -> dict[str, Any]:
    """
    Extract top-level metadata from ADE result for document record updates.
    Returns a dict with: parser_version, page_count, credit_usage, ade_job_id.
    """
    metadata = ade_result.get("metadata", {})
    return {
        "parser_version": metadata.get("version", "unknown"),
        "page_count": metadata.get("page_count", 0),
        "credit_usage": float(metadata.get("credit_usage", 0.0)),
        "ade_job_id": metadata.get("job_id", ""),
        "duration_ms": metadata.get("duration_ms", 0),
        "failed_pages": metadata.get("failed_pages", []),
    }
