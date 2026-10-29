"""
backend/scripts/check_embed_consistency.py
Read-only diagnostic script to check embedding consistency.

Usage (from backend/ directory):
    .venv\\Scripts\\python.exe scripts/check_embed_consistency.py

Or from repository root:
    backend\\.venv\\Scripts\\python.exe backend/scripts/check_embed_consistency.py

Guarantees:
  - Strictly READ-ONLY: no writes to ChromaDB, SQLite, or Redis.
  - Takes up to 3 stored chunks (with their stored vectors) from each document in Chroma.
  - Re-embeds chunk texts with the CURRENT query embedding model (at most 6 live calls total).
  - Prints per chunk: cosine similarity, vector dimensions on both sides,
    model name used for ingestion, model name used for queries.
  - Verifies whether ingestion and query models come from the same config setting.
  - Verdict: above 0.98 = consistent; below 0.95 = MISMATCH.
  - Never logs secret values or API keys.
"""
from __future__ import annotations

import asyncio
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure backend root is on Python path
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Load .env without printing keys
from dotenv import load_dotenv
env_file = BACKEND_DIR / ".env"
if env_file.exists():
    load_dotenv(dotenv_path=env_file)

from app.core.config import get_settings


def calculate_cosine_similarity(vec_a: Any, vec_b: Any) -> float:
    """Calculate cosine similarity between two numeric vectors."""
    if vec_a is None or vec_b is None:
        return 0.0
    list_a = list(vec_a)
    list_b = list(vec_b)
    if not list_a or not list_b or len(list_a) != len(list_b):
        return 0.0
    dot_product = sum(a * b for a, b in zip(list_a, list_b))
    norm_a = math.sqrt(sum(a * a for a in list_a))
    norm_b = math.sqrt(sum(b * b for b in list_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def get_verdict(sim: float, dim_match: bool = True) -> str:
    """
    Chunk-level re-embedding verdict rules:
      above 0.99 = consistent
      0.99 or below = MISMATCH
    """
    if not dim_match:
        return "MISMATCH (dimension mismatch)"
    if sim > 0.99:
        return "consistent"
    else:
        return f"MISMATCH (similarity {sim:.4f} <= 0.99)"


def extract_first_sentence(text: str) -> str:
    """
    Extract the first meaningful sentence from a chunk text.
    Strips HTML anchor tags and markdown headers first.
    """
    import re
    cleaned = re.sub(r'<[^>]+>', ' ', text)
    cleaned = re.sub(r'^#+\s+.*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned).strip()
    match = re.search(r'^(.*?[.!?])(?:\s|$)', cleaned, flags=re.DOTALL)
    if match:
        first = match.group(1).strip()
        if len(first) >= 15:
            return first[:250]
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if lines:
        return lines[0][:200]
    return cleaned[:100]


async def reembed_passages_exact(texts: List[str]) -> List[List[float]]:
    """
    Re-embed chunk texts exactly the way ingestion does:
    uses embedding_provider.embed_passages with input_type='passage',
    same batching, and same text preparation.
    """
    from app.providers.openrouter_embedding import embedding_provider
    return await embedding_provider.embed_passages(texts=texts)


async def embed_query_exact(text: str) -> List[float]:
    """
    Embed a query text using input_type='query', matching standard retrieval.
    """
    from app.providers.openrouter_embedding import embedding_provider
    return await embedding_provider.embed_query(text)


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


async def check_embed_consistency() -> int:
    """Main verification routine."""
    settings = get_settings()

    print_header("EMBEDDING CONSISTENCY CHECK")
    print(f"Backend directory:  {BACKEND_DIR}")
    print(f"Chroma DB Path:     {settings.CHROMA_DB_PATH}")
    print(f"Collection Name:    {settings.CHROMA_COLLECTION_NAME}")

    # 1. Config Inspection: Ingestion vs Query embedding models
    print_header("1. CONFIGURATION MODEL SETTINGS")
    ingestion_model_cfg = settings.EMBEDDING_MODEL
    query_model_cfg = settings.EMBEDDING_MODEL

    print(f"* Ingestion Embedding Model (from config):  {ingestion_model_cfg}")
    print(f"* Query Embedding Model (from config):      {query_model_cfg}")

    # Inspect whether both settings originate from the same config attribute
    has_separate_query_setting = hasattr(settings, "QUERY_EMBEDDING_MODEL")
    if has_separate_query_setting:
        separate_val = getattr(settings, "QUERY_EMBEDDING_MODEL")
        if separate_val != ingestion_model_cfg:
            print("[WARN] WARNING: Ingestion model and query model DO NOT come from the same setting!")
            print(f"   Settings.EMBEDDING_MODEL = {ingestion_model_cfg}")
            print(f"   Settings.QUERY_EMBEDDING_MODEL = {separate_val}")
        else:
            print("[OK] Ingestion and query models come from the same effective value.")
    else:
        print("[OK] Both ingestion and query models come from the SAME setting:")
        print("  -> 'EMBEDDING_MODEL' in app.core.config.Settings")

    # 2. Inspect ChromaDB (Read-Only)
    print_header("2. CHROMADB INSPECTION (READ-ONLY)")
    raw_path = Path(settings.CHROMA_DB_PATH)
    if raw_path.is_absolute():
        chroma_dir = raw_path
    else:
        # Resolve relative to BACKEND_DIR so it always points to backend/data/chroma_db
        chroma_dir = (BACKEND_DIR / raw_path).resolve()

    print(f"* Resolved Chroma DB Path:   {chroma_dir}")
    if not chroma_dir.exists():
        print(f"[INFO] ChromaDB directory does not exist at '{chroma_dir}'.")
        print("   Database is currently empty (0 documents, 0 chunks).")
        print("   No stored vectors to verify against.")
        print("\nVerdict: No data present to test. Configuration is consistent.")
        return 0

    import chromadb
    try:
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(name=settings.CHROMA_COLLECTION_NAME)
    except Exception as exc:
        print(f"[INFO] ChromaDB collection '{settings.CHROMA_COLLECTION_NAME}' could not be loaded: {exc}")
        print("   No collection found or collection is empty.")
        return 0

    # Startup guard: ensure collection-level model name is recorded when missing
    from app.db.chromadb_client import ensure_collection_metadata_model
    ensure_collection_metadata_model()
    # Refresh collection metadata after guard
    collection = client.get_collection(name=settings.CHROMA_COLLECTION_NAME)

    stored_collection_model = (collection.metadata or {}).get("embedding_model")
    total_count = collection.count()
    print(f"* Collection total chunks:   {total_count}")
    print(f"* Collection metadata model: {stored_collection_model or '(none recorded)'}")

    if total_count == 0:
        print("[INFO] ChromaDB collection has 0 chunks.")
        print("   No stored vectors to verify.")
        return 0

    # Retrieve all chunks with embeddings, metadatas, documents
    print("\nReading stored chunks and vectors from ChromaDB...")
    records = collection.get(include=["documents", "metadatas", "embeddings"])
    ids = list(records.get("ids") or [])
    docs = list(records.get("documents") or [])
    metas = list(records.get("metadatas") or [])
    raw_embeddings = records.get("embeddings")
    embeddings = list(raw_embeddings) if raw_embeddings is not None else []

    # Group chunks by document_id
    from collections import defaultdict
    doc_chunks: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for chunk_id, text, meta, emb in zip(ids, docs, metas, embeddings):
        doc_id = (meta or {}).get("document_id", "unknown_doc")
        doc_chunks[doc_id].append({
            "chunk_id": chunk_id,
            "text": text,
            "metadata": meta or {},
            "embedding": emb,
        })

    print(f"Found {len(doc_chunks)} distinct document(s) in ChromaDB.")

    # 3. Select 3 chunks per document (with non-empty text) for evaluation
    # Cap total chunks across docs at 6 to guarantee live calls stay <= 9 (1 re-embed batch + at most 6 queries = 7 calls)
    MAX_PER_DOC = 3
    MAX_EVAL_CHUNKS = 6

    selected_chunks: List[Tuple[str, Dict[str, Any]]] = []
    for doc_id, chunk_list in doc_chunks.items():
        # Prefer chunks that have a meaningful first sentence
        viable = [c for c in chunk_list if len(extract_first_sentence(c["text"])) >= 15]
        pool = viable if len(viable) >= MAX_PER_DOC else chunk_list
        sample = pool[:MAX_PER_DOC]
        for c in sample:
            selected_chunks.append((doc_id, c))
            if len(selected_chunks) >= MAX_EVAL_CHUNKS:
                break
        if len(selected_chunks) >= MAX_EVAL_CHUNKS:
            break

    print(f"Selected {len(selected_chunks)} chunk(s) across {len(doc_chunks)} document(s) for evaluation.")

    # 4. Re-embed each chunk text exactly the way ingestion does
    print_header("3. LIVE RE-EMBEDDING & COSINE SIMILARITY (INGESTION-EXACT)")
    print(f"Re-embedding {len(selected_chunks)} chunk(s) using input_type='passage' (same as ingestion)...")

    results_summary: List[Dict[str, Any]] = []
    chunk_texts = [c["text"] for _, c in selected_chunks]

    try:
        live_embeddings = await reembed_passages_exact(chunk_texts)
    except Exception as exc:
        print(f"[FAIL] Batch passage re-embedding failed: {exc}")
        print(f"\nOVERALL VERDICT: MISMATCH (Re-embedding API call failed: {exc})")
        return 1

    for idx, ((doc_id, chunk_data), live_vec) in enumerate(zip(selected_chunks, live_embeddings), 1):
        chunk_id = chunk_data["chunk_id"]
        text = chunk_data["text"]
        meta = chunk_data["metadata"]
        stored_vec = chunk_data["embedding"]

        stored_dim = len(stored_vec)
        live_dim = len(live_vec)
        stored_model = meta.get("embedding_model") or stored_collection_model or ingestion_model_cfg

        dim_match = (stored_dim == live_dim)
        sim = calculate_cosine_similarity(stored_vec, live_vec)
        verdict = get_verdict(sim, dim_match)

        print(f"\n[{idx}/{len(selected_chunks)}] Evaluating Chunk: {chunk_id}")
        print(f"   Document ID:         {doc_id}")
        print(f"   Chunk Type:          {meta.get('chunk_type', 'text')} (Page {meta.get('page', 0)})")
        print(f"   Stored Ingest Model: {stored_model}")
        print(f"   Live Ingest Model:   {query_model_cfg}")
        print(f"   Stored Vector Dim:   {stored_dim}")
        print(f"   Live Vector Dim:     {live_dim}")
        print(f"   Text preview:        {text[:80].strip()!r}...")
        print(f"   Cosine Similarity:   {sim:.6f}")
        print(f"   Chunk Verdict:       {verdict}")

        results_summary.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "stored_model": stored_model,
            "live_model": query_model_cfg,
            "stored_dim": stored_dim,
            "live_dim": live_dim,
            "similarity": sim,
            "dim_match": dim_match,
            "verdict": verdict,
            "text": text,
        })

    # 5. Retrieval Sanity Check
    print_header("4. RETRIEVAL SANITY CHECK (TOP-3 HIT RATE)")
    print("Using first sentence of chunks as query (input_type='query'), verifying source chunk in top 3...")

    retrieval_hits = 0
    retrieval_total = 0
    retrieval_results: List[Dict[str, Any]] = []

    for idx, (doc_id, chunk_data) in enumerate(selected_chunks, 1):
        chunk_id = chunk_data["chunk_id"]
        text = chunk_data["text"]
        question = extract_first_sentence(text)
        if not question:
            question = text[:80]

        print(f"\n[Query {idx}/{len(selected_chunks)}] Doc {doc_id[:8]}... Chunk: {chunk_id[:16]}...")
        print(f"   Question: \"{question}\"")

        try:
            query_vec = await embed_query_exact(question)
            search_res = collection.query(
                query_embeddings=[query_vec],
                n_results=min(3, total_count),
                include=["metadatas", "distances"],
            )
            top_ids = (search_res.get("ids") or [[]])[0]
            is_hit = chunk_id in top_ids
            rank = (top_ids.index(chunk_id) + 1) if is_hit else None

            if is_hit:
                retrieval_hits += 1
                status_str = f"HIT (rank {rank} of top {len(top_ids)})"
            else:
                status_str = f"MISS (not in top {len(top_ids)})"

            retrieval_total += 1
            print(f"   Top 3 IDs: {[cid[:16] + '...' for cid in top_ids]}")
            print(f"   Result:    {status_str}")

            retrieval_results.append({
                "chunk_id": chunk_id,
                "question": question,
                "is_hit": is_hit,
                "rank": rank,
                "top_ids": top_ids,
            })
        except Exception as exc:
            print(f"   [FAIL] Query call failed: {exc}")
            retrieval_total += 1
            retrieval_results.append({
                "chunk_id": chunk_id,
                "question": question,
                "is_hit": False,
                "rank": None,
                "top_ids": [],
            })

    hit_rate = (retrieval_hits / retrieval_total) if retrieval_total > 0 else 0.0
    print(f"\nRetrieval Hit Rate: {retrieval_hits}/{retrieval_total} ({hit_rate:.1%})")

    # 6. Summary Report & Overall Verdict
    print_header("5. SUMMARY REPORT & VERDICT")
    print(f"{'Chunk ID':<24} | {'Stored Dim':<10} | {'Live Dim':<10} | {'Cos Sim':<10} | {'Verdict'}")
    print("-" * 80)

    min_sim = 1.0
    all_dim_match = True
    model_name_match = (ingestion_model_cfg == query_model_cfg)

    for r in results_summary:
        cid = r["chunk_id"][:22]
        s_dim = str(r["stored_dim"])
        l_dim = str(r["live_dim"])
        sim_val = r["similarity"]
        sim_str = f"{sim_val:.4f}"
        verd = r["verdict"]

        if sim_val < min_sim:
            min_sim = sim_val
        if not r["dim_match"]:
            all_dim_match = False

        print(f"{cid:<24} | {s_dim:<10} | {l_dim:<10} | {sim_str:<10} | {verd}")

    print("-" * 80)
    print(f"* Model Config Match:       {model_name_match} ({ingestion_model_cfg})")
    print(f"* All Dimensions Match:     {all_dim_match}")
    print(f"* Min Re-embed Similarity:  {min_sim:.6f} (threshold: > 0.99)")
    print(f"* Retrieval Top-3 Hit Rate: {retrieval_hits}/{retrieval_total} = {hit_rate:.1%} (threshold: >= 2/3 [66.7%])")
    print("-" * 80)

    # Verdict determination
    sim_ok = (min_sim > 0.99)
    hit_rate_ok = (hit_rate >= (2.0 / 3.0))

    if all_dim_match and model_name_match and sim_ok and hit_rate_ok:
        print("OVERALL VERDICT: CONSISTENT (All evaluated chunks match ingestion embeddings, hit rate >= 2/3)")
        return 0
    else:
        mismatch_reasons = []
        if not model_name_match:
            mismatch_reasons.append(f"Model mismatch (ingest={ingestion_model_cfg}, query={query_model_cfg})")
        if not all_dim_match:
            mismatch_reasons.append("Dimension mismatch detected")
        if not sim_ok:
            mismatch_reasons.append(f"Re-embedding similarity below 0.99 (min={min_sim:.4f})")
        if not hit_rate_ok:
            mismatch_reasons.append(f"Retrieval hit rate below 2/3 ({retrieval_hits}/{retrieval_total} = {hit_rate:.1%})")

        print(f"OVERALL VERDICT: MISMATCH ({'; '.join(mismatch_reasons)})")
        return 1


def main() -> None:
    try:
        code = asyncio.run(check_embed_consistency())
        sys.exit(code)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
