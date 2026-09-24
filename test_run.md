# Test Run Guide — Multimodal RAG Platform (Days 0–4)

> **Status built:** Day 0 Foundation · Day 1 Upload + Ingestion · Day 2 ADE + Chunking · Day 3 Embedding + ChromaDB · **Day 4 Query Router + Retrieval**  
> **Stack:** FastAPI (Python 3.12) · React + Vite · LandingAI ADE · ChromaDB · OpenRouter (NVIDIA Nemotron Embed)

---

## Day 0 — Foundation & Project Setup

### 0.1 Prerequisites

| Requirement | Value |
|---|---|
| Python | 3.12+ |
| Node.js | 18+ |
| Redis | Local or Upstash (TLS `rediss://` URL) |
| `OPENROUTER_API_KEY` | Required from Day 3 onwards |
| `LANDINGAI_API_KEY` | Required from Day 2 onwards |
| `GROQ_API_KEY` | Required from Day 5 onwards |

**Verify `backend/.env` has all required keys:**
```env
OPENROUTER_API_KEY=sk-or-v1-...
LANDINGAI_API_KEY=...
GROQ_API_KEY=...
REDIS_URL=rediss://default:...
EMBEDDING_MODEL=nvidia/llama-nemotron-embed-vl-1b-v2:free
EMBEDDING_BATCH_SIZE=16
ADE_MODEL=dpt-2-latest
```

### 0.2 Start the Backend

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend
.venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected startup logs:**
```
INFO  Starting Multimodal RAG API    version=0.1.0
INFO  ChromaDB initialized           collection=ade_documents  existing_chunks=0
INFO  Redis connected successfully
INFO  All services initialized. Ready to serve.
INFO  Uvicorn running on http://0.0.0.0:8000
```

> [!NOTE]
> `existing_chunks=0` on a fresh start is expected. After uploading documents, this number
> reflects all previously indexed chunks on server restart.

### 0.3 Start the Frontend

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

### 0.4 Health Check

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health"
```

**Expected:**
```json
{ "status": "ok", "chromadb": true, "redis": true }
```

---

## Day 1 — Upload + Async Ingestion + Job Tracking

### 1.1 Automated Tests

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend
.venv\Scripts\python.exe -m pytest tests/test_health.py tests/test_ingestion.py -v
```

**Expected:** All tests pass (~21 tests).

### 1.2 Register and Login

1. Navigate to **http://localhost:5173**
2. Register a new account (username + email + password)
3. Log in with those credentials
4. Verify the navbar shows **Documents** and **Ask a Question**

### 1.3 Upload a Document

1. Navigate to the **Documents** page
2. Drag and drop any PDF (e.g. `2_table_budget_report.pdf`) onto the upload zone
3. Verify the status badge cycles: `Pending` → `Processing` → `Completed`

**Expected backend logs:**
```
INFO  File saved       document_id=sha256...  filename=2_table_budget_report.pdf
INFO  Job created      job_id=...  status=pending
INFO  Ingestion started
INFO  Ingestion completed  status=completed
```

### 1.4 Idempotency — Upload the Same File Again

Upload the same file a second time.

**Expected:** Same `document_id` returned, no duplicate job created.

### 1.5 API — Upload via Swagger

Go to **http://localhost:8000/docs** → `POST /api/v1/documents/upload`

- Try uploading a `.txt` file → `415 Unsupported Media Type`
- Try uploading a file > `MAX_UPLOAD_SIZE_MB` → `413 Request Entity Too Large`

### 1.6 Job Status Polling

```powershell
$token = "<your_jwt_token>"
$jobId = "<job_id_from_upload_response>"
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/jobs/$jobId" `
  -Headers @{ Authorization = "Bearer $token" }
```

**Expected:** `status` field transitions from `pending` → `processing` → `completed`.

---

## Day 2 — ADE Integration + Multimodal Chunk Normalization

> [!NOTE]
> LandingAI ADE parses documents into structured chunks: `text`, `table`, and `figure`.
> Each chunk has a `bbox [x0, y0, x1, y1]` (normalized 0–1) and a `page` number (0-indexed).

### 2.1 Automated Tests

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend
.venv\Scripts\python.exe -m pytest tests/test_chunking.py -v
```

**Expected:** 13/13 passed.

### 2.2 Verify ADE Output Files

After uploading a PDF, check that ADE output files are created on disk:

```powershell
$docId = "<your_document_id>"
Get-ChildItem "data\ade_outputs\$docId"
```

**Expected files:**
```
raw.json      ← raw ADE API response
document.md   ← full document as markdown
chunks.json   ← normalized chunks in production schema
```

### 2.3 Inspect Chunk Schema

```powershell
Get-Content "data\ade_outputs\$docId\chunks.json" | ConvertFrom-Json | Select-Object -First 1
```

**Expected fields per chunk:**
```json
{
  "chunk_id": "sha256...",
  "document_id": "sha256...",
  "chunk_type": "text",
  "text": "...",
  "page": 0,
  "bbox": [0.12, 0.07, 0.86, 0.32],
  "source": "2_table_budget_report.pdf",
  "parser_version": "dpt-2-20260410",
  "ade_chunk_id": "ade_internal_id",
  "confidence": 0.967
}
```

### 2.4 ADE Idempotency (Cache Hit)

Upload the same document a second time.

**Expected backend log:**
```
INFO  ADE cache hit — skipping API call
```

ADE is NOT called again — zero credits spent.

### 2.5 View Details Panel (Frontend)

After a document completes, click **▼ View Details** on the document card.

**Expected panel:**
```
Filename        2_table_budget_report.pdf
File Type       PDF
Total Chunks    🧩 3
Parser Version  dpt-2-20260410
ADE Credits     💳 3.00
Document ID     sha256...
Status          ✅ Completed
```

### 2.6 Error Cases

| Test | Expected |
|---|---|
| Upload non-PDF/DOCX/image | `415 Unsupported Media Type` |
| `LANDINGAI_API_KEY` invalid | Job → `failed`, error logged |
| ADE API timeout | Retries 3× with backoff, then job → `failed` |

---

## Day 3 — Multimodal Embeddings + ChromaDB Indexing

> [!NOTE]
> **What Day 3 added:** After chunking, each chunk is embedded using **NVIDIA Llama-Nemotron-Embed-VL-1B-V2**
> (via OpenRouter) in `passage` mode and stored in ChromaDB. This enables semantic search —
> find chunks by meaning, not just keywords.

### 3.1 Automated Tests

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend
.venv\Scripts\python.exe -m pytest tests/test_embedding.py -v
```

**Expected:** 7/7 passed (all mocked — no real API calls).

### 3.2 Upload a Document and Verify Embedding Logs

Upload any PDF. Watch the backend logs for the embedding phase (new in Day 3):

```
# ── Phase 1: ADE Parsing ─────────────────────────────
INFO  ADE parse complete         chunk_count=4  credit_usage=3.0
INFO  Chunking complete          chunk_count=4

# ── Phase 2: Embedding ────────────────────────────────
INFO  Loaded chunks for embedding    total_chunks=4
INFO  Embedding idempotency check    total=4  new=4  skipped=0
INFO  Embedding new chunks           model=nvidia/llama-nemotron-embed-vl-1b-v2:free
INFO  ChromaDB upsert complete       count=4  collection=ade_documents
INFO  Embedding complete             new_chunks_indexed=4  latency_ms=1240.5

# ── Phase 3: Completed ────────────────────────────────
INFO  Ingestion completed        embedding_model=nvidia/llama-nemotron-embed-vl-1b-v2:free
```

### 3.3 Verify ChromaDB Contains the Chunks

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend
.venv\Scripts\python.exe
```

```python
import chromadb, json

client = chromadb.PersistentClient(path="data/chroma_db")
collection = client.get_collection("ade_documents")

print("Total indexed chunks:", collection.count())

result = collection.get(limit=1, include=["metadatas", "documents"])
print("\nFirst chunk text:", result["documents"][0][:150])
print("\nMetadata:", json.dumps(result["metadatas"][0], indent=2))
```

**Expected:**
```
Total indexed chunks: 4

Metadata:
{
  "document_id": "sha256...",
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
> `bbox` is stored as 4 separate scalar fields in ChromaDB (its metadata can only hold scalars).
> The API reconstructs it as `[x0, y0, x1, y1]` for all consumers.

### 3.4 Fetch a Single Chunk via API

```powershell
$token = "<your_jwt_token>"
$docId = (Get-ChildItem "data\ade_outputs" -Directory)[0].Name
$chunkId = (Get-Content "data\ade_outputs\$docId\chunks.json" | ConvertFrom-Json)[0].chunk_id

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/documents/$docId/chunks/$chunkId" `
  -Headers @{ Authorization = "Bearer $token" }
```

**Expected response:**
```json
{
  "chunk_id": "sha256...",
  "document_id": "sha256...",
  "chunk_type": "text",
  "text": "Revenue for Q3...",
  "page": 0,
  "bbox": [0.145, 0.069, 0.853, 0.105],
  "source": "mixed_sample.pdf",
  "parser_version": "dpt-2-20260410"
}
```

### 3.5 Embedding Idempotency — Re-upload Same File

Upload the same document a second time.

**Expected backend log:**
```
INFO  ADE cache hit — skipping API call
INFO  Embedding idempotency check    total=4  new=0  skipped=4
INFO  All chunks already indexed — skipping embedding API calls
```

Zero ADE credits + zero OpenRouter credits spent on re-upload.

### 3.6 View Details Panel — Embedding Model Field

After a document completes, open **▼ View Details**.

**New field (added in Day 3):**
```
Embedding Model  🧠 nvidia/llama-nemotron-embed-vl-1b-v2
```

### 3.7 Error Cases

| Test | Expected |
|---|---|
| `GET /chunks/{chunk_id}` with wrong chunk_id | `404 Not Found` |
| `GET /chunks/{chunk_id}` with wrong doc_id | `404 Not Found` |
| `OPENROUTER_API_KEY` invalid | Job → `failed`, embedding error logged |
| OpenRouter rate limit (429) | Retries 3× with backoff, then job → `failed` |
| ChromaDB directory not writable | Server fails to start |

### 3.8 Manual Semantic Search Preview (ChromaDB Python)

```python
import chromadb, httpx, asyncio, os

# Load env
env = {}
with open(".env") as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v

client = chromadb.PersistentClient(path="data/chroma_db")
collection = client.get_collection("ade_documents")
print(f"Collection has {collection.count()} chunks")

async def embed_query(text):
    async with httpx.AsyncClient() as http:
        r = await http.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {env['OPENROUTER_API_KEY']}"},
            json={"model": "nvidia/llama-nemotron-embed-vl-1b-v2:free", "input": [text], "input_type": "query"},
            timeout=30.0,
        )
        return r.json()["data"][0]["embedding"]

q_emb = asyncio.run(embed_query("What was the revenue?"))
results = collection.query(query_embeddings=[q_emb], n_results=3, include=["documents", "metadatas", "distances"])

for i, (doc, meta, dist) in enumerate(zip(results["documents"][0], results["metadatas"][0], results["distances"][0])):
    print(f"\n#{i+1}  similarity={round(1-dist,4)}  page={meta['page']}  type={meta['chunk_type']}")
    print(doc[:120])
```

**Expected:** Top-3 chunks ranked by cosine similarity to the query.

---

## Day 4 — Query Router + Text/Multimodal/Hybrid Retrieval

> [!IMPORTANT]
> **What Day 4 added:** `POST /query` is now live. It accepts a natural-language question,
> routes it to a retrieval strategy (text / multimodal / hybrid), embeds the query using
> NVIDIA Nemotron in **query mode**, searches ChromaDB for the Top-N most similar chunks,
> and returns them as grounded source citations.
>
> The answer field contains a Day-4 placeholder. The real LLM-generated answer is wired in Day 5.

---

### How the Query Router Works

| Route | Trigger | Strategy |
|-------|---------|----------|
| 📝 **Text** | No visual keywords | Single ChromaDB similarity search, all chunk types |
| 🖼️ **Multimodal** | `table`, `chart`, `figure`, `image`, `graph`, `plot`, `diagram`, `visual`, `picture`, `scan`, `handwritten`, `layout`, `column`, `row` | Single ChromaDB similarity search, all chunk types |
| ⚡ **Hybrid** | Visual keyword + connective (`and`, `also`, `both`) OR query ≥ 8 words | TWO ChromaDB queries (text-only + visual-only), merged, deduplicated, re-sorted by score |

> [!NOTE]
> Routing is purely deterministic — keyword matching only, zero LLM calls. Routing takes < 1 ms.

---

### How Top-N Retrieval Works

```
User query: "What was the total revenue?"
      ↓  embed in query mode → [0.08, -0.41, 0.79, ...]
      ↓  cosine similarity vs all indexed chunk vectors in ChromaDB
┌────────────────────────────────────────────────┐
│  #1  chunk_id: abc123  score: 0.912  type: text   │
│  #2  chunk_id: def456  score: 0.884  type: table  │
│  ...                                              │
│  #20 chunk_id: xyz000  score: 0.501  type: figure │
└────────────────────────────────────────────────┘
```

Day 5 reranks these 20 candidates and picks the best 5 for the LLM.

---

### 4.1 Automated Tests

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend

# Day 4 retrieval tests only (16 tests, ~10s)
.venv\Scripts\python.exe -m pytest tests/test_retrieval.py -v

# All mocked tests Days 0–4 (excludes live ADE + model tests)
.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_ade.py --ignore=tests/test_models.py -v

# Full suite including live model connectivity
.venv\Scripts\python.exe -m pytest tests/ -v
```

**Expected Day 4 test output:**
```
tests/test_retrieval.py::test_route_text                    PASSED
tests/test_retrieval.py::test_route_text_general            PASSED
tests/test_retrieval.py::test_route_multimodal              PASSED
tests/test_retrieval.py::test_route_multimodal_figure       PASSED
tests/test_retrieval.py::test_route_hybrid_connective       PASSED
tests/test_retrieval.py::test_route_hybrid_long_query       PASSED
tests/test_retrieval.py::test_route_case_insensitive        PASSED
tests/test_retrieval.py::test_route_multiple_keywords       PASSED
tests/test_retrieval.py::test_retrieve_text_calls_chroma    PASSED
tests/test_retrieval.py::test_retrieve_multimodal_no_filter PASSED
tests/test_retrieval.py::test_retrieve_hybrid_two_queries   PASSED
tests/test_retrieval.py::test_retrieve_hybrid_deduplicates  PASSED
tests/test_retrieval.py::test_retrieve_hybrid_sorted        PASSED
tests/test_retrieval.py::test_document_ids_single_filter    PASSED
tests/test_retrieval.py::test_document_ids_multi_filter     PASSED
tests/test_retrieval.py::test_top_n_respected               PASSED

16 passed in ~10s
```

**Overall after Day 4:** `63 passed` (full suite, excluding 1 pre-existing `test_ade.py::test_parse_sample` fixture error unrelated to Day 4).

### 4.2 Open the Query Page

1. Start backend and frontend (same commands as Days 0–3)
2. Log in at **http://localhost:5173**
3. Click **💬 Ask a Question** in the navbar

**Expected UI (Day 4 — no longer a disabled stub):**
- Live textarea with placeholder text
- **🔍 Ask Question** button enabled (Ctrl+Enter shortcut)
- **🗂️ Filter to specific documents** chip pills (one per completed document)
- Empty state: `💡 Ask a question to get grounded answers with source citations.`

### 4.3 Text Route Query

Type in the textarea:
```
What is the total revenue?
```

Click **Ask Question** or press **Ctrl+Enter**.

**Expected results panel:**
- Route tag: **📝 Text**
- Latency indicator: e.g. `⏱ 1285 ms`
- Candidate count: e.g. `20 candidates`
- Answer box:
  ```
  [Day 4 — retrieval only] Found 20 candidate chunk(s) via 'text' route.
  LLM-generated answer will be available from Day 5.
  ```
- **📎 Retrieved Chunks** section — up to 20 collapsible source cards

**Source card (collapsed):**
```
#1  📄 Text   Page 3   91.2% match  ▼
```

**Source card (expanded):**
```
"Q3 net revenue reached $4.2 billion..."

Chunk ID   abc12345678...
Doc ID     sha256abc12...
BBox       [0.14, 0.07, 0.85, 0.11]
```

### 4.4 Multimodal Route Query

Type:
```
Show me the revenue table
```

**Expected:**
- Route tag: **🖼️ Multimodal**
- Source cards may include `📊 Table` and `🖼️ Figure` type badges

> [!TIP]
> All multimodal trigger keywords: `table`, `chart`, `figure`, `image`, `graph`, `plot`,
> `diagram`, `visual`, `picture`, `scan`, `handwritten`, `layout`, `column`, `row`

### 4.5 Hybrid Route Query

Type:
```
Describe the chart and its text caption
```

**Expected:**
- Route tag: **⚡ Hybrid**
- Mix of `📄 Text` and `📊 Table`/`🖼️ Figure` cards
- Backend log shows two ChromaDB queries:
  ```
  INFO  Retrieval complete  strategy=hybrid  results_count=20  text_raw=20  visual_raw=3
  ```

> [!NOTE]
> `text_raw=20  visual_raw=3` — text query found 20 candidates, visual query found 3.
> After merge + dedup + re-sort, the best 20 unique chunks are returned.

### 4.6 Document Filter

If multiple documents are uploaded:

1. Click a **document chip** in the query form — it turns blue with ✓
2. Ask any question — only chunks from selected documents are retrieved
3. Leave chips unselected to search **all** documents

**Backend log confirmation:**
```
INFO  Query received   document_ids=['abc123...']  top_n=20
```

### 4.7 Debug Raw Candidates Toggle

After receiving results:

1. Click **🔓 Show raw candidates** (appears next to Submit after first result)
2. **🔬 Raw Retrieval Debug** panel expands:
   - Embed latency, retrieval latency, route used
   - Table: `# | Chunk ID | Type | Page | Score | Preview` for all candidates
3. Click **🔒 Hide** to collapse

### 4.8 API Test via Swagger (`POST /query`)

Go to **http://localhost:8000/docs** → Authorize with JWT.

**Minimal request (text route):**
```json
{ "query": "What was the total revenue?" }
```

**With document scope:**
```json
{
  "query": "Show me the budget table",
  "document_ids": ["<your_document_id>"]
}
```

**With custom top_k:**
```json
{ "query": "Describe the figure", "top_k": 5 }
```

**Expected 200 response:**
```json
{
  "answer": "[Day 4 — retrieval only] Found 20 candidate chunk(s) via 'text' route. LLM-generated answer will be available from Day 5.",
  "sources": [
    {
      "document_id": "abc123...",
      "chunk_id": "sha256...",
      "page": 2,
      "bbox": [0.14, 0.07, 0.85, 0.11],
      "chunk_type": "text",
      "text_preview": "Q3 net revenue reached $4.2 billion...",
      "relevance_score": 0.912,
      "filename": ""
    }
  ],
  "route_type": "text",
  "cache_hit": false,
  "model_used": "",
  "provider_used": "",
  "latency": {
    "total_ms": 1285.4,
    "query_embed_ms": 1240.1,
    "retrieval_ms": 44.8,
    "reranking_ms": 0.0,
    "llm_ms": 0.0
  }
}
```

**Error cases:**

| Test | Expected |
|------|----------|
| No `Authorization` header | `401 Unauthorized` |
| Empty `query` string | `422 Unprocessable Entity` |
| `query` > 2000 chars | `422 Unprocessable Entity` |
| `top_k` > 20 | `422 Unprocessable Entity` |
| Valid query, empty ChromaDB | `200` with `sources: []` |

### 4.9 PowerShell Verification Commands

```powershell
# Get token
$loginResult = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
  -Method POST -ContentType "application/x-www-form-urlencoded" `
  -Body "username=yourusername&password=yourpassword"
$token = $loginResult.access_token

# Text route — verify route_type, candidate count, latency
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/query" `
  -Method POST `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body '{"query": "What is the total revenue?"}' |
  Select-Object route_type, @{n="candidates";e={$_.sources.Count}}, @{n="latency_ms";e={$_.latency.total_ms}}

# Multimodal route
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/query" `
  -Method POST `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body '{"query": "Show me the revenue table"}' | Select-Object route_type

# Hybrid route
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/query" `
  -Method POST `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body '{"query": "Describe the chart and its text caption"}' | Select-Object route_type
```

**Expected output:**
```
route_type  candidates  latency_ms
----------  ----------  ----------
text        20          1285.4

route_type    route_type
----------    ----------
multimodal    hybrid
```

### 4.10 Log Reading Guide — Day 4 Query Pipeline

Full structured log for one query:

```
INFO  Query received         user_id=u123  query_preview="What was the revenue?"  top_n=20

# Step 1: Routing (< 1 ms)
INFO  Query routed           route=text  keyword_hits=[]  word_count=5

# Step 2: Embed query in query mode (~1–2 sec)
DEBUG Calling OpenRouter embeddings API  input_type=query  batch_size=1
INFO  Embedding batch complete           latency_ms=1198.4  total_tokens=8

# Step 3: ChromaDB similarity search (~40–80 ms)
INFO  Retrieval complete     strategy=text  results_count=20  latency_ms=44.2

# Pipeline complete
INFO  Query pipeline complete (Day 4 — pre-rerank)
      route=text  candidates=20  embed_ms=1198.4  retrieval_ms=44.2  total_ms=1244.5
```

**For a hybrid query:**
```
INFO  Query routed      route=hybrid  keyword_hits=['chart']  word_count=9
INFO  Retrieval complete  strategy=hybrid  results_count=20  text_raw=20  visual_raw=3
```

> [!TIP]
> `total_ms ≈ embed_ms + retrieval_ms`. Embedding dominates (1–2 sec per query).
> In Day 6, Redis cache eliminates the entire pipeline for repeat queries.

---

## Pipeline Status — What Is Built vs What Remains

| Day | Feature | Status |
|---|---|---|
| 0 | Foundation: FastAPI skeleton, React skeleton, ChromaDB init, Redis init, all schemas | ✅ Built |
| 1 | Upload + Jobs: `POST /documents/upload`, async ingestion, job status, frontend upload form | ✅ Built |
| 2 | ADE + Chunking: real ADE integration, multimodal chunks with bbox/page/type preserved | ✅ Built |
| 3 | Embeddings + Index: OpenRouter NVIDIA embeddings, ChromaDB indexing, idempotency | ✅ Built |
| 4 | Router + Retrieval: query router (text/multimodal/hybrid), Top-N candidates via ChromaDB | ✅ Built |
| 5 | Rerank + LLM: OpenRouter reranker, context assembly, Qwen 27B + Nemotron fallback, grounded answer | Not built |
| 6 | Redis Cache: query-answer caching, cache invalidation on re-ingestion | Not built |
| 7 | Observability: 5 benchmark categories, SQLite persistence, `/metrics` endpoint | Not built |
| 8 | Evaluation + Hardening: Recall@K / Precision@K, Docker Compose, rate limiting, full polish | Not built |

The `POST /query` endpoint returns a **placeholder answer** (Day 4). Day 5 replaces it with
a real grounded LLM answer. All source citations, route tags, latency breakdowns, and
similarity scores are already real as of Day 4.

---

## Component Change Log

| Component | Added in Day | Description |
|---|---|---|
| FastAPI skeleton, all schemas | Day 0 | Full project structure, Pydantic models, CORS, health endpoint |
| JWT auth (register/login) | Day 0 | bcrypt passwords, jose JWT tokens |
| `POST /documents/upload` | Day 1 | SHA-256 dedup, MIME validation, size enforcement, BackgroundTasks |
| `GET /jobs/{job_id}` | Day 1 | Async job status polling |
| `services/ingestion_service.py` | Day 1 | Orchestrates ADE → chunking → embedding → completion |
| `providers/ade.py` | Day 2 | Real LandingAI ADE httpx integration with retry |
| `services/chunking_service.py` | Day 2 | Normalize ADE output → `Chunk` schema with bbox/page/type |
| `providers/openrouter_embedding.py` | Day 3 | Batched NVIDIA Nemotron embed (passage + query modes) |
| `db/chromadb_client.py` | Day 3 | Full CRUD: upsert, cosine query, get by ID, delete, stats |
| `services/embedding_service.py` | Day 3 | Load → idempotency check → embed → upsert pipeline |
| `GET /documents/{id}/chunks/{chunk_id}` | Day 3 | Fetch single chunk from ChromaDB |
| `services/query_router.py` | Day 4 | Deterministic keyword router → text / multimodal / hybrid |
| `services/retrieval_service.py` | Day 4 | Three retrieval strategies; hybrid merges two ChromaDB queries |
| `POST /query` | Day 4 | Route → embed (query mode) → retrieve Top-N → return candidates |
| `QueryPage.jsx` + `QueryPage.css` | Day 4 | Full query UI: doc selector, route tag, source cards, debug toggle |
| `tests/test_retrieval.py` | Day 4 | 16 mocked tests (8 router + 8 retrieval strategies) |
