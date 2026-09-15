"""
backend/app/schemas/chunk.py
Pydantic models for multimodal chunks.
Preserves: document_id, chunk_type, page, bbox, text, source, parser_version.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field


class ChunkType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    UNKNOWN = "unknown"


BBox = List[float]  # [x0, y0, x1, y1] normalized 0–1


class Chunk(BaseModel):
    """
    Production multimodal chunk with full provenance.
    Extends the notebook's {chunk_id, chunk_type, text, bbox, page}
    with document-level and system provenance fields.
    """
    chunk_id: str = Field(
        ...,
        description="Stable ID = SHA-256(document_id + page + str(bbox) + chunk_type)"
    )
    document_id: str = Field(..., description="Parent document identifier")
    chunk_type: ChunkType = Field(..., description="Content modality: text | table | figure")
    text: str = Field(..., description="Chunk text content (HTML for tables, description for figures)")
    page: int = Field(..., description="0-indexed page number in source document")
    bbox: BBox = Field(
        default_factory=list,
        description="Bounding box [x0, y0, x1, y1] normalized to [0, 1]"
    )
    source: str = Field(default="", description="Source filename/path")
    parser_version: str = Field(default="", description="ADE parser version that produced this chunk")

    # Optional: image data for figure/table chunks (base64 or URL)
    image_data: Optional[str] = Field(
        default=None,
        description="Base64 image data for visual chunk types (figure, table with visual)"
    )

    class Config:
        use_enum_values = True


class ChunkResponse(BaseModel):
    """API response for a single chunk lookup."""
    chunk_id: str
    document_id: str
    chunk_type: str
    text: str
    page: int
    bbox: BBox
    source: str
    parser_version: str


class ChunksListResponse(BaseModel):
    chunks: list[ChunkResponse]
    total: int
