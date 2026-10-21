"""
backend/tests/test_chroma_chunks.py
Inspection helper and test for ChromaDB collection access.
"""
import os
from pathlib import Path
import chromadb
from app.core.config import get_settings


def test_chroma_collection_access():
    """Verify ChromaDB client connects to isolated collection and can query."""
    settings = get_settings()
    chroma_path = settings.get_chroma_db_path()
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    assert collection is not None
    assert collection.count() >= 0


def main():
    settings = get_settings()
    chroma_path = settings.get_chroma_db_path()
    print(f"Looking for ChromaDB at: {chroma_path}")
    print(f"Exists: {chroma_path.exists()}\n")

    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_collection("ade_documents")
    print(f"Total indexed chunks: {collection.count()}")
    all_chunks = collection.get(include=["metadatas", "documents"])
    print(f"\nTotal chunks retrieved: {len(all_chunks['ids'])}")


if __name__ == "__main__":
    main()
