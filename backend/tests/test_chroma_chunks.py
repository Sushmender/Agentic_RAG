import chromadb
import json
from pathlib import Path

CHROMA_PATH = Path(__file__).parent.parent / "data" / "chroma_db"

print(f"Looking for ChromaDB at: {CHROMA_PATH}")
print(f"Exists: {CHROMA_PATH.exists()}\n")

client = chromadb.PersistentClient(path=str(CHROMA_PATH))
collection = client.get_collection("ade_documents")

print(f"Total indexed chunks: {collection.count()}")

# Get ALL chunks from the database
all_chunks = collection.get(
    include=["metadatas", "documents"]
)

print(f"\nTotal chunks retrieved: {len(all_chunks['ids'])}")
for i, (doc, meta) in enumerate(zip(all_chunks["documents"], all_chunks["metadatas"])):
    print(f"\n--- Chunk {i+1} ---")
    print(f"  Type: {meta['chunk_type']}, Page: {meta['page']}")
    print(f"  Source: {meta['source']}")
    print(f"  Parser Version: {meta.get('parser_version', 'N/A')}")
    print(f"  Text preview: {doc[:150]}")
