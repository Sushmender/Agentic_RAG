# Test Run Guide — Multimodal RAG Platform (Day 0 + 1 + 2 + 3)

> **Status built:** Foundation · Upload + Ingestion · ADE + Chunking · **Embedding + ChromaDB Indexing**  
> **Stack:** FastAPI (Python 3.12) · React + Vite · LandingAI ADE · ChromaDB · OpenRouter (NVIDIA Nemotron Embed)

---

## ✅ Stage 1 — Already Done (Days 0–2)

> [!NOTE]
> **You have already completed this stage.** It covers:
> - Backend + Frontend project setup
> - JWT authentication (register / login)
> - Document upload with MIME validation and SHA-256 dedup
> - LandingAI ADE document parsing (PDF/DOCX/images → structured chunks)
> - Chunk normalization to `chunks.json` (text / table / figure)
> - In-memory document + job stores
> - 34 passing automated tests

If you haven't already, follow the steps in the **old sections 1–5** (Prerequisites → Manual Tests 5.1–5.10) to get the system running and confirm it's healthy before proceeding to Stage 2.

---

## 🚀 Stage 2 — Today's Tasks: Embedding + ChromaDB Indexing (Day 3)

> [!IMPORTANT]
> **What changes today:** Every document you upload now gets its chunks automatically
> **embedded** (converted into a list of numbers representing meaning) using the
> **NVIDIA Llama-Nemotron-Embed-VL-1B-V2** model (via OpenRouter), then stored
> in **ChromaDB** so they can be searched by similarity later.
>
> Think of it like this: previously, your document was parsed into text chunks and saved to disk.
> Today, those chunks also get a "fingerprint" (the embedding vector) stored in a database
> that supports semantic search. When you later ask a question, your question gets the same
> "fingerprint" treatment and the closest-matching chunks are retrieved.

---

### 🧠 What Is an Embedding (Plain English)?

An **embedding** is a list of numbers (e.g. 1024 floats) that captures the *meaning* of a piece of text.

```
"The company revenue grew 20% this quarter"
       ↓  NVIDIA Nemotron model
[0.12, -0.45, 0.87, 0.33, ..., 0.02]   ← 1024 numbers = "meaning fingerprint"
```

Two sentences that mean similar things will produce similar lists of numbers (close vectors),
even if they use completely different words.

```
"revenue grew 20%"  →  [0.12, -0.45, 0.87, ...]
"earnings up by a fifth"  →  [0.11, -0.43, 0.85, ...]   ← very similar!
```

**Passage vs Query mode** — this model uses two different modes:

| Mode | Used For | Example |
|---|---|---|
| `passage` | Embedding document chunks at index time | "Q3 net revenue was $4.2B" |
| `query` | Embedding the user's question at search time | "What was the revenue?" |

This distinction is **critical** — using the wrong mode would make retrieval much less accurate.

---

### 🗄️ What Is ChromaDB (Plain English)?

ChromaDB is the **vector database** — it stores each chunk alongside its embedding vector.

```
ChromaDB "ade_documents" collection:

chunk_id: "abc123"
text:     "Q3 net revenue was $4.2B, up 20% YoY"
embedding: [0.12, -0.45, 0.87, 0.33, ..., 0.02]   ← 1024 floats
metadata:
  document_id:    "sha256..."
  chunk_type:     "text"
  page:           2
  bbox_x0:        0.145
  bbox_y0:        0.069
  bbox_x1:        0.853
  bbox_y1:        0.105
  source:         "annual_report.pdf"
  parser_version: "dpt-2-20260410"
```

When you search later, ChromaDB finds the chunks whose embedding vectors are closest
to your query's vector — this is **semantic search** (find by meaning, not just keywords).

---

## 1. Prerequisites (New for Stage 2)

In addition to the existing prerequisites, you now need:

| Requirement | Check |
|---|---|
| `OPENROUTER_API_KEY` in `backend/.env` | Must be set — embedding costs real API credits |
| `EMBEDDING_MODEL` in `backend/.env` | Should be `nvidia/llama-nemotron-embed-vl-1b-v2:free` |
| `EMBEDDING_BATCH_SIZE` in `backend/.env` | Defaults to `16` if not set |
| ChromaDB writes OK | `data/chroma_db/` directory must be writable |

**Verify your `.env` has these entries:**
```env
OPENROUTER_API_KEY=sk-or-v1-...
EMBEDDING_MODEL=nvidia/llama-nemotron-embed-vl-1b-v2:free
EMBEDDING_BATCH_SIZE=16
```

---

## 2. Start the Backend

Same as before — no change needed:

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend

.venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8000
```

**Updated startup output (look for the new embedding log line):**
```
INFO  Starting Multimodal RAG API version=0.1.0
INFO  ChromaDB initialized  collection=ade_documents  existing_chunks=0
INFO  Redis ping successful
INFO  All services initialized. Ready to serve.
INFO  Uvicorn running on http://0.0.0.0:8000
```

> [!NOTE]
> `existing_chunks=0` on first run is expected — the ChromaDB collection is empty.
> After you upload a document, this number will reflect previously indexed chunks on restart.

---

## 3. Start the Frontend

Same as before:

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## 4. Automated Tests (Updated for Day 3)

Run from **`backend/`** — no server or real API calls needed (all mocked):

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend

# All tests including new Day 3 embedding tests (45 total)
.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_ade.py -v

# Just the new Day 3 embedding tests (7 tests, fastest)
.venv\Scripts\python.exe -m pytest tests/test_embedding.py -v

# Full suite including live ADE connectivity test
.venv\Scripts\python.exe -m pytest tests/ -v
```

**Expected output for embedding tests:**
```
tests/test_embedding.py::test_embed_passages_batching                   PASSED
tests/test_embedding.py::test_embed_query_single_vector                  PASSED
tests/test_embedding.py::test_chromadb_upsert_idempotency               PASSED
tests/test_embedding.py::test_embedding_service_skips_existing           PASSED
tests/test_embedding.py::test_embedding_service_new_chunks               PASSED
tests/test_embedding.py::test_get_chunk_by_id                            PASSED
tests/test_embedding.py::test_ingestion_pipeline_includes_embedding      PASSED

7 passed in ~3s
```

**Overall:** `45 passed` (up from 34 in Stage 1).

> [!IMPORTANT]
> The 7 embedding tests use **mocked API calls** — they test the logic (batching,
> idempotency, metadata mapping) without calling OpenRouter or spending credits.
> This means tests are fast, free, and deterministic.

---

## 5. Manual Test Checklist

### 5.1–5.9 — All Previous Tests Still Work

Everything from Stage 1 (health check, login, upload, View Details, idempotency, error cases)
works exactly the same. Run them first to confirm nothing regressed.

---

### 5.10 — NEW: Upload a Document and Watch Embedding Happen

This is the most important Stage 2 test. Upload any PDF and watch the full pipeline:

1. Log in and navigate to the Documents page
2. Upload `backend/sample_docs/mixed_sample.pdf`
3. Watch the status badge cycle through:
   - `Pending` → `Processing` → *(new)* `Embedding chunks into ChromaDB` → `Complete`

**Watch the backend terminal logs — you will now see NEW log lines:**

```
INFO  Ingestion started              document_id=abc123...
INFO  Calling ADE provider           model=dpt-2-latest
INFO  ADE parse complete             chunk_count=4  credit_usage=3.0
INFO  Persisted raw.json
INFO  Persisted document.md
INFO  Chunk normalization complete   total_normalized=4  skipped_empty=0
INFO  Persisted chunks.json          chunk_count=4
INFO  Chunking complete              chunk_count=4  credits_used=3.0

# ↓ NEW lines from Day 3 ↓
INFO  Loaded chunks for embedding    total_chunks=4
INFO  Embedding idempotency check    total=4  new=4  skipped=0
INFO  Embedding new chunks           new_chunks=4  batch_size=16  model=nvidia/...
INFO  ChromaDB upsert complete       count=4  collection=ade_documents
INFO  Embedding complete             new_chunks_indexed=4  skipped_chunks=0  latency_ms=1240.5

INFO  Ingestion completed            chunk_count=4  embedding_model=nvidia/llama-nemotron-embed-vl-1b-v2:free
```

> [!TIP]
> Notice `latency_ms` — embedding 4 chunks typically takes 1–3 seconds.
> For large documents (50+ chunks), expect 10–30 seconds total for embedding.

---

### 5.11 — NEW: Verify Embedding Model in View Details Panel

After a document completes, open **▼ View Details**. You should now see a new row:

```
┌─────────────────────────────────────────────────────┐
│  Filename        mixed_sample.pdf                    │
│  File Type       PDF                                 │
│  File Size       245 KB                              │
│  Total Chunks    🧩 4                                │
│  Parser Version  dpt-2-20260410                      │
│  ADE Credits     💳 3.00                             │
│  Embedding Model 🧠 nvidia/llama-nemotron-embed-vl-1b-v2   ← NEW!
│  Document ID     abc123def456...                     │
│  Status          ✅ Completed                        │
└─────────────────────────────────────────────────────┘
```

> [!NOTE]
> The `:free` suffix is hidden in the UI display for cleanliness — `nvidia/llama-nemotron-embed-vl-1b-v2`
> is what you see. The actual model called is `nvidia/llama-nemotron-embed-vl-1b-v2:free`.

---

### 5.12 — NEW: Verify ChromaDB Contains the Chunks

After upload completes, verify the chunks landed in ChromaDB:

```powershell
# Open a Python shell in the backend venv
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend
.venv\Scripts\python.exe
```

```python
import chromadb

# Connect to the persistent ChromaDB
client = chromadb.PersistentClient(path="data/chroma_db")
collection = client.get_collection("ade_documents")

# How many chunks are indexed?
print("Total indexed chunks:", collection.count())

# Peek at the first chunk's metadata
result = collection.get(limit=1, include=["metadatas", "documents"])
print("\nFirst chunk text:")
print(result["documents"][0][:200])

print("\nFirst chunk metadata:")
import json
print(json.dumps(result["metadatas"][0], indent=2))
```

**Expected output:**
```
Total indexed chunks: 4

First chunk text:
<a id='page-0-text-0'></a>

Revenue for Q3 2025 reached $4.2 billion...

First chunk metadata:
{
  "document_id": "abc123def456...",
  "chunk_id": "sha256...",
  "chunk_type": "text",
  "page": 0,
  "bbox_x0": 0.145,
  "bbox_y0": 0.069,
  "bbox_x1": 0.853,
  "bbox_y1": 0.105,
  "source": "mixed_sample.pdf",
  "parser_version": "dpt-2-20260410"
}
```

> [!NOTE]
> Notice the bbox is stored as **4 separate scalar fields** (`bbox_x0`, `bbox_y0`, `bbox_x1`, `bbox_y1`)
> rather than a list. This is a ChromaDB requirement — it can only store scalar values (numbers, strings)
> in metadata, not lists or nested objects.

---

### 5.13 — NEW: Fetch a Single Chunk via API

You can now look up any individual chunk by its ID:

```powershell
# First, get a chunk_id from the ChromaDB check above, or from chunks.json
$docId = (Get-ChildItem backend\data\ade_outputs -Directory)[0].Name
$chunkId = (Get-Content "backend\data\ade_outputs\$docId\chunks.json" |
  ConvertFrom-Json)[0].chunk_id

# Get your JWT token first (from login)
$token = "eyJhbGc..."

# Fetch the chunk from the API
curl -H "Authorization: Bearer $token" `
  "http://localhost:8000/api/v1/documents/$docId/chunks/$chunkId"
```

**Expected response:**
```json
{
  "chunk_id": "abc123...",
  "document_id": "sha256...",
  "chunk_type": "text",
  "text": "<a id='page-0-text-0'></a>\n\nRevenue for Q3...",
  "page": 0,
  "bbox": [0.145, 0.069, 0.853, 0.105],
  "source": "mixed_sample.pdf",
  "parser_version": "dpt-2-20260410"
}
```

> [!NOTE]
> Notice that the API **reconstructs** the `bbox` as a list `[x0, y0, x1, y1]` from
> the 4 scalar fields stored in ChromaDB. The API consumer always sees a clean list,
> never the internal `bbox_x0/y0/x1/y1` split.

**Error cases to test:**

```powershell
# Wrong document ID → 404
curl -H "Authorization: Bearer $token" \
  "http://localhost:8000/api/v1/documents/wrongdocid/chunks/$chunkId"
# → 404: "Document 'wrongdocid' not found."

# Chunk from a different document → 404 (security check)
curl -H "Authorization: Bearer $token" \
  "http://localhost:8000/api/v1/documents/$docId/chunks/nonexistent_chunk"
# → 404: "Chunk 'nonexistent_chunk' not found in ChromaDB."
```

---

### 5.14 — NEW: Idempotency — Upload Same File Again

Upload `mixed_sample.pdf` a **second time**. This now tests embedding idempotency too:

**Backend logs should show:**
```
INFO  ADE cache hit — skipping API call
INFO  Loaded chunks for embedding    total_chunks=4
INFO  Embedding idempotency check    total=4  new=0  skipped=4
INFO  All chunks already indexed — skipping embedding API calls   skipped=4
INFO  Ingestion completed            new_chunks_indexed=0  skipped_chunks=4
```

**What this means:**
- ADE is NOT called (SHA-256 cache hit)
- All 4 chunk IDs already exist in ChromaDB → `get_existing_ids()` returns all 4
- `new=0` → embedding API is NOT called (0 OpenRouter credits spent)
- The whole second upload takes < 1 second

> [!TIP]
> This is idempotency in action — you can safely re-upload the same document
> at any time without worrying about double-billing on ADE credits or embedding API costs.

---

### 5.15 — NEW: Semantic Search Preview (Manual ChromaDB Test)

You can manually test that the embeddings enable semantic search, even before the
query endpoint is built in Day 4:

```python
# In the backend/.venv Python shell
import chromadb
import httpx
import asyncio
import json

# Load your OpenRouter API key
with open("backend/.env") as f:
    env = dict(line.strip().split("=", 1) for line in f if "=" in line and not line.startswith("#"))

client = chromadb.PersistentClient(path="data/chroma_db")
collection = client.get_collection("ade_documents")

# Quick check — what's in there?
print(f"Collection has {collection.count()} chunks")
```

```python
# Build a fake query embedding using the same model
async def get_query_embedding(text: str) -> list:
    async with httpx.AsyncClient() as http:
        response = await http.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {env['OPENROUTER_API_KEY']}"},
            json={
                "model": "nvidia/llama-nemotron-embed-vl-1b-v2:free",
                "input": [text],
                "input_type": "query",   # ← "query" mode for search
            },
            timeout=30.0,
        )
        data = response.json()
        return data["data"][0]["embedding"]

# Get the embedding for a question
question = "What was the revenue?"
q_embedding = asyncio.run(get_query_embedding(question))
print(f"Query embedding dimension: {len(q_embedding)}")

# Search ChromaDB for the closest chunks
results = collection.query(
    query_embeddings=[q_embedding],
    n_results=3,
    include=["documents", "metadatas", "distances"],
)

print("\nTop 3 semantically similar chunks:")
for i, (doc, meta, dist) in enumerate(zip(
    results["documents"][0],
    results["metadatas"][0],
    results["distances"][0],
)):
    similarity = round(1 - dist, 4)   # ChromaDB returns cosine distance
    print(f"\n--- Result {i+1} (similarity={similarity}) ---")
    print(f"Page: {meta['page']}, Type: {meta['chunk_type']}")
    print(doc[:150] + "...")
```

**Expected output:**
```
Query embedding dimension: 1024

Top 3 semantically similar chunks:

--- Result 1 (similarity=0.8412) ---
Page: 2, Type: text
<a id='page-2-text-0'></a>
Q3 net revenue reached $4.2 billion, a 20% increase year-over-year...

--- Result 2 (similarity=0.7931) ---
Page: 3, Type: table
<table><tr><th>Quarter</th><th>Revenue</th>...

--- Result 3 (similarity=0.6214) ---
Page: 1, Type: text
...
```

> [!TIP]
> The query `"What was the revenue?"` finds chunks about revenue even if they
> say "net earnings", "quarterly income", or "financial results" — because
> the model understands **meaning**, not just keywords.

---

### 5.16 — NEW: API Swagger Tests (Updated)

Go to **http://localhost:8000/docs** and test the new endpoint:

#### `GET /api/v1/documents/{document_id}/chunks/{chunk_id}` ← **NEW**
- Authorize first with your JWT token
- Get a valid `document_id` from `GET /documents/`
- Get a valid `chunk_id` from `data/ade_outputs/{id}/chunks.json`
- Should return a `ChunkResponse` with all fields including `bbox` as a list
- Try a non-existent `chunk_id` → `404 Not Found`
- Try a `chunk_id` that belongs to a different document → `404 Not Found`

---

### 5.17 — NEW: Log Reading Guide (Updated for Day 3)

Full ingestion + embedding log flow for a new document:

```
# ── Phase 1: ADE Parsing ──────────────────────────────
Ingestion started          document_id=abc  status=processing
Calling ADE provider       model=dpt-2-latest  file=mixed_sample.pdf
ADE parse complete         chunk_count=4  credit_usage=3.0  page_count=1
Persisted raw.json
Persisted document.md
Chunk normalization complete  total_normalized=4  skipped_empty=0
Persisted chunks.json      chunk_count=4

# ── Phase 2: Embedding (NEW in Day 3) ─────────────────
Loaded chunks for embedding       total_chunks=4
Embedding idempotency check       total=4  new=4  skipped=0
Embedding new chunks              new_chunks=4  model=nvidia/llama-nemotron-embed-vl-1b-v2:free
  Calling OpenRouter embeddings API   batch_start=0  batch_size=4  input_type=passage
  Embedding batch complete            latency_ms=1240.5  total_tokens=312
ChromaDB upsert complete          count=4  collection=ade_documents
Embedding complete                new_chunks_indexed=4  latency_ms=1255.0

# ── Phase 3: Mark Completed ───────────────────────────
Ingestion completed        chunk_count=4  embedding_model=nvidia/...  status=completed

# ── Re-upload (idempotency) ───────────────────────────
ADE cache hit — skipping API call
Embedding idempotency check       total=4  new=0  skipped=4
All chunks already indexed — skipping embedding API calls
Ingestion completed        new_chunks_indexed=0  skipped_chunks=4
```

---

## 6. Error Cases (New for Stage 2)

| Test | Expected Behavior |
|---|---|
| `GET /chunks/{chunk_id}` with bad chunk_id | `404 Not Found` — "Chunk not found in ChromaDB" |
| `GET /chunks/{chunk_id}` with wrong doc ID | `404 Not Found` — "does not belong to document" |
| Upload without `OPENROUTER_API_KEY` set | Job fails with `401` from OpenRouter — job → `failed`, error logged |
| OpenRouter rate limit hit (429) | Embedding retries up to 3× with backoff, then job → `failed` |
| ChromaDB directory not writable | Server fails to start at initialization |

---

## 7. What Is NOT Yet Built

| Day | Feature | Status |
|---|---|---|
| 4 | Query router + retrieval (text / multimodal / hybrid) | Not built |
| 5 | Reranker + LLM answer generation (Groq / OpenRouter) | Not built |
| 6 | Redis query-answer cache | Not built |
| 7 | Observability + SQLite persistence | Not built |
| 8 | RAG evaluation + Docker Compose | Not built |

The **`/query`** page exists but returns a stub. The **Query →** button on each document
card navigates there — it won't produce answers yet. But after today (Day 3), the
**embedding vectors are ready and waiting** in ChromaDB — Day 4 simply needs to
search them with a query embedding.

---

## 8. Quick Summary: What Day 3 Added

| Component | Before Day 3 | After Day 3 |
|---|---|---|
| `providers/openrouter_embedding.py` | Stub (raised NotImplementedError) | Real batched embedding with passage/query modes |
| `db/chromadb_client.py` | Init + health only | Full CRUD: upsert, query, get by ID, delete, get existing IDs |
| `services/embedding_service.py` | Did not exist | New orchestrator: load → idempotency check → embed → upsert |
| `services/ingestion_service.py` | Stopped after chunks.json | Now calls `index_chunks()` as Step 9 before marking Complete |
| `GET /documents/{id}/chunks/{chunk_id}` | Raised NotImplementedError | Real ChromaDB fetch with document ownership check |
| `DocumentMetadata` schema | No embedding info | New `embedding_model` field |
| View Details panel (UI) | No embedding info | Shows `🧠 nvidia/llama-nemotron-embed-vl-1b-v2` |
| Tests | 34 passing | **45 passing** (+7 new embedding tests, all mocked) |
