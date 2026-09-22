"""
backend/app/db/chromadb_client.py
ChromaDB persistent client — full CRUD for Day 3.

Collection: ade_documents
Distance metric: cosine (hnsw:space=cosine)

Metadata schema (all values must be scalar for ChromaDB):
  document_id:    str
  chunk_id:       str
  chunk_type:     str   ("text" | "table" | "figure")
  page:           int
  bbox_x0:        float
  bbox_y0:        float
  bbox_x1:        float
  bbox_y1:        float
  source:         str
  parser_version: str

Key design decisions:
  - upsert_chunks() is idempotent — same chunk_ids are safely overwritten
  - get_existing_ids() used by embedding_service to skip already-indexed chunks
  - delete_document() removes all chunks for a document (used on re-ingestion)
  - query_similar() supports optional `where` dict for metadata filtering
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import chromadb
from chromadb.api.models.Collection import Collection

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.chunk import Chunk

logger = get_logger(__name__)
settings = get_settings()

# Module-level ChromaDB client and collection (initialized on startup)
_chroma_client: Optional[chromadb.ClientAPI] = None
_collection: Optional[Collection] = None


# ── Initialization ─────────────────────────────────────────────────────────────

def get_chroma_client() -> chromadb.ClientAPI:
    """Return the initialized ChromaDB client (persistent or ephemeral in tests)."""
    global _chroma_client
    if _chroma_client is None:
        raise RuntimeError("ChromaDB client not initialized. Call init_chromadb() first.")
    return _chroma_client


def get_collection() -> Collection:
    """Return the main ChromaDB collection for document chunks."""
    global _collection
    if _collection is None:
        raise RuntimeError("ChromaDB collection not initialized. Call init_chromadb() first.")
    return _collection


def init_chromadb(client: Optional[chromadb.ClientAPI] = None) -> None:
    """
    Initialize ChromaDB persistent client and create/load the 'ade_documents' collection.
    Called once on application startup (or with a custom client in tests).

    Args:
        client: Optional pre-built ChromaDB client (e.g. EphemeralClient for tests).
                If None, creates a PersistentClient using settings.CHROMA_DB_PATH.
    """
    global _chroma_client, _collection

    if client is not None:
        _chroma_client = client
    else:
        db_path = str(settings.get_chroma_db_path())
        logger.info("Initializing ChromaDB (persistent)", path=db_path)
        _chroma_client = chromadb.PersistentClient(path=db_path)

    _collection = _chroma_client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},  # cosine similarity
    )

    count = _collection.count()
    logger.info(
        "ChromaDB initialized",
        collection=settings.CHROMA_COLLECTION_NAME,
        existing_chunks=count,
    )


# ── Write operations ───────────────────────────────────────────────────────────

def upsert_chunks(
    chunks: List[Chunk],
    embeddings: List[List[float]],
) -> int:
    """
    Upsert chunks with their embeddings into ChromaDB.
    Idempotent: existing chunk_ids are safely overwritten with new data.

    Args:
        chunks:     List of normalized Chunk objects.
        embeddings: Embedding vectors in the same order as chunks.

    Returns:
        Number of chunks upserted.
    """
    if not chunks:
        return 0

    collection = get_collection()

    ids = [c.chunk_id for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [_chunk_to_metadata(c) for c in chunks]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    logger.info(
        "ChromaDB upsert complete",
        count=len(chunks),
        collection=settings.CHROMA_COLLECTION_NAME,
    )
    return len(chunks)


def delete_document(document_id: str) -> int:
    """
    Remove ALL chunks for a given document from ChromaDB.
    Called when a document is re-ingested to invalidate stale embeddings.

    Returns:
        Number of chunks deleted.
    """
    collection = get_collection()

    # First, count how many exist so we can return an accurate count
    existing = collection.get(
        where={"document_id": document_id},
        include=[],
    )
    count = len(existing.get("ids", []))

    if count > 0:
        collection.delete(where={"document_id": document_id})
        logger.info(
            "ChromaDB document deleted",
            document_id=document_id,
            chunks_deleted=count,
        )
    return count


# ── Read operations ────────────────────────────────────────────────────────────

def get_existing_ids(chunk_ids: List[str]) -> Set[str]:
    """
    Check which of the given chunk_ids already exist in ChromaDB.
    Used by embedding_service to skip already-indexed chunks (idempotency).

    Returns:
        Set of chunk_ids that are already in the collection.
    """
    if not chunk_ids:
        return set()

    collection = get_collection()
    result = collection.get(ids=chunk_ids, include=[])
    return set(result.get("ids", []))


def get_chunk_by_id(chunk_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single chunk by its chunk_id.

    Returns:
        Dict with keys: chunk_id, document_id, chunk_type, page, bbox,
        text, source, parser_version — or None if not found.
    """
    collection = get_collection()
    result = collection.get(
        ids=[chunk_id],
        include=["documents", "metadatas"],
    )

    ids = result.get("ids", [])
    if not ids:
        return None

    metadata = (result.get("metadatas") or [{}])[0]
    document = (result.get("documents") or [""])[0]

    # Reconstruct bbox list from scalar fields
    bbox = [
        float(metadata.get("bbox_x0", 0.0)),
        float(metadata.get("bbox_y0", 0.0)),
        float(metadata.get("bbox_x1", 0.0)),
        float(metadata.get("bbox_y1", 0.0)),
    ]

    return {
        "chunk_id": ids[0],
        "document_id": metadata.get("document_id", ""),
        "chunk_type": metadata.get("chunk_type", "text"),
        "page": int(metadata.get("page", 0)),
        "bbox": bbox,
        "text": document,
        "source": metadata.get("source", ""),
        "parser_version": metadata.get("parser_version", ""),
    }


def query_similar(
    embedding: List[float],
    n_results: int = 20,
    where: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Cosine similarity search in ChromaDB.

    Args:
        embedding:  Query embedding vector.
        n_results:  Number of top results to return.
        where:      Optional ChromaDB metadata filter dict.

    Returns:
        List of result dicts with: chunk_id, document_id, chunk_type,
        page, bbox, text, source, similarity_score.
    """
    collection = get_collection()

    # Guard against querying an empty collection
    if collection.count() == 0:
        return []

    kwargs: Dict[str, Any] = {
        "query_embeddings": [embedding],
        "n_results": min(n_results, collection.count()),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    result = collection.query(**kwargs)

    ids_list = (result.get("ids") or [[]])[0]
    metas_list = (result.get("metadatas") or [[]])[0]
    docs_list = (result.get("documents") or [[]])[0]
    dists_list = (result.get("distances") or [[]])[0]

    output: List[Dict[str, Any]] = []
    for chunk_id, meta, doc, dist in zip(ids_list, metas_list, docs_list, dists_list):
        bbox = [
            float(meta.get("bbox_x0", 0.0)),
            float(meta.get("bbox_y0", 0.0)),
            float(meta.get("bbox_x1", 0.0)),
            float(meta.get("bbox_y1", 0.0)),
        ]
        # ChromaDB cosine distance → similarity: similarity = 1 - distance
        similarity = round(1.0 - float(dist), 6)
        output.append({
            "chunk_id": chunk_id,
            "document_id": meta.get("document_id", ""),
            "chunk_type": meta.get("chunk_type", "text"),
            "page": int(meta.get("page", 0)),
            "bbox": bbox,
            "text": doc,
            "source": meta.get("source", ""),
            "parser_version": meta.get("parser_version", ""),
            "similarity_score": similarity,
        })

    return output


# ── Stats & Health ─────────────────────────────────────────────────────────────

def get_collection_stats() -> Dict[str, Any]:
    """Return stats about the collection including total count."""
    collection = get_collection()
    total = collection.count()

    return {
        "collection_name": collection.name,
        "total_chunks": total,
    }


def is_healthy() -> bool:
    """Check if ChromaDB is accessible and collection is available."""
    try:
        get_collection().count()
        return True
    except Exception as exc:
        logger.error("ChromaDB health check failed", error=str(exc))
        return False


# ── Internal helpers ───────────────────────────────────────────────────────────

def _chunk_to_metadata(chunk: Chunk) -> Dict[str, Any]:
    """
    Convert a Chunk object to a ChromaDB-compatible metadata dict.
    All values must be scalar (str, int, float, bool).
    bbox [x0, y0, x1, y1] is stored as 4 separate float fields.
    """
    bbox = chunk.bbox if chunk.bbox and len(chunk.bbox) == 4 else [0.0, 0.0, 0.0, 0.0]
    return {
        "document_id": chunk.document_id,
        "chunk_id": chunk.chunk_id,
        "chunk_type": str(chunk.chunk_type),
        "page": int(chunk.page),
        "bbox_x0": float(bbox[0]),
        "bbox_y0": float(bbox[1]),
        "bbox_x1": float(bbox[2]),
        "bbox_y1": float(bbox[3]),
        "source": chunk.source or "",
        "parser_version": chunk.parser_version or "",
    }

