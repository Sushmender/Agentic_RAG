"""
backend/app/db/chromadb_client.py
ChromaDB persistent client initialization.
Provides the vector store for multimodal chunk embeddings.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import chromadb
from chromadb.api.models.Collection import Collection

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Module-level ChromaDB client and collection (initialized on startup)
_chroma_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[Collection] = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Return the initialized ChromaDB persistent client."""
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


def init_chromadb() -> None:
    """
    Initialize ChromaDB persistent client and create/load the 'ade_documents' collection.
    Called once on application startup.
    """
    global _chroma_client, _collection

    db_path = str(settings.get_chroma_db_path())
    logger.info("Initializing ChromaDB", path=db_path)

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


def get_collection_stats() -> Dict[str, Any]:
    """Return basic stats about the collection."""
    collection = get_collection()
    return {
        "collection_name": collection.name,
        "total_chunks": collection.count(),
    }


def is_healthy() -> bool:
    """Check if ChromaDB is accessible and collection is available."""
    try:
        get_collection().count()
        return True
    except Exception as exc:
        logger.error("ChromaDB health check failed", error=str(exc))
        return False
