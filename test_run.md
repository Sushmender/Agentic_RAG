# Test Run Guide — Multimodal RAG Platform (Days 0–9)

> **Status built:** Day 0 Foundation · Day 1 Upload + Ingestion · Day 2 ADE + Chunking · Day 3 Embedding + ChromaDB · Day 4 Query Router + Retrieval · Day 5 Reranking + Context Assembly + LLM Generation · Day 6 Redis Cache Pipeline · Day 7 Telemetry + SQLite Persistence + Metrics Dashboard · Day 8 RAG Evaluation + Source Grounding · **Day 9 Production Hardening & Documentation**  
> **Stack:** FastAPI (Python 3.12) · React + Vite · LandingAI ADE · ChromaDB · OpenRouter (NVIDIA Nemotron Embed + Reranker + Nemotron 120B) · Groq (Qwen 3.8 27B) · Redis / Upstash · SQLite (aiosqlite) · JSONL telemetry

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
| `GROQ_API_KEY` | Required from Day 5 onwards ✅ |

**Verify `backend/.env` has all required keys:**
```env
OPENROUTER_API_KEY=sk-or-v1-...
LANDINGAI_API_KEY=...
GROQ_API_KEY=gsk_...
REDIS_URL=rediss://default:...
EMBEDDING_MODEL=nvidia/llama-nemotron-embed-vl-1b-v2:free
RERANKER_MODEL=nvidia/llama-nemotron-rerank-vl-1b-v2:free
FALLBACK_LLM_MODEL=nvidia/nemotron-3-super-120b-a12b:free
PRIMARY_LLM_MODEL=qwen/qwen3.8-27b
EMBEDDING_BATCH_SIZE=16
RERANK_TOP_K=5
MAX_CONTEXT_TOKENS=8000
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

## Day 5 — Reranking + Context Assembly + LLM Generation

> [!IMPORTANT]
> **What Day 5 added:** The complete answer pipeline is now live. `POST /query` goes all the way:
> **Route → Embed → Retrieve (Top-20) → Rerank (Top-5) → Assemble grounded context → Generate answer**
>
> - **Reranker:** `nvidia/llama-nemotron-rerank-vl-1b-v2:free` via OpenRouter — scores 20 candidates, returns Top-5
> - **Primary LLM:** `qwen/qwen3.8-27b` via Groq — fast inference, grounded prompt
> - **Fallback LLM:** `nvidia/nemotron-3-super-120b-a12b:free` via OpenRouter — activated automatically if Groq fails
> - **Reranker failure:** logs the error, skips reranking, LLM still generates an answer from raw retrieval order
> - **Frontend:** Provider selector dropdown (Groq / Nemotron), model badge with tokens + cost

---

### How the Day 5 Pipeline Works

```
User query: "What is the total revenue?"
       ↓
 [Route] → text
       ↓
 [Embed query] → [0.08, -0.41, ...]  (NVIDIA Nemotron, query mode)
       ↓
 [Retrieve Top-20] → 20 candidates from ChromaDB by cosine similarity
       ↓
 [Rerank Top-5] → nvidia/llama-nemotron-rerank-vl-1b-v2:free
                  Input: query + 20 candidate texts
                  Output: 5 chunks sorted by relevance_score desc
       ↓
 [Assemble context] → Token-budget check (len//4 estimate)
                      Build grounded prompt:
                      [Source 1 — page 3, type: text]  <chunk text>
                      [Source 2 — page 1, type: table] <chunk text>
                      ...
                      QUESTION: What is the total revenue?
                      ANSWER:
       ↓
 [Generate] → Try Groq (qwen/qwen3.8-27b)
              On any failure → OpenRouter (nemotron-3-super-120b-a12b:free)
       ↓
 QueryResponse: { answer, sources[5], model_used, provider_used, latency, token_usage, cost_usd }
```

---

### 5.1 Automated Tests

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend

# Day 5 tests only (21 tests, ~8s, all mocked)
.venv\Scripts\python.exe -m pytest tests/test_query_pipeline.py -v

# Full suite Days 0–5 (84 pass, 1 pre-existing ADE fixture error)
.venv\Scripts\python.exe -m pytest tests/ -v
```

**Expected Day 5 test output:**
```
tests/test_query_pipeline.py::TestFullPipeline::test_query_returns_200_with_answer          PASSED
tests/test_query_pipeline.py::TestFullPipeline::test_response_schema_complete               PASSED
tests/test_query_pipeline.py::TestFullPipeline::test_latency_fields_all_present             PASSED
tests/test_query_pipeline.py::TestFullPipeline::test_sources_have_correct_schema            PASSED
tests/test_query_pipeline.py::TestFullPipeline::test_token_usage_populated                  PASSED
tests/test_query_pipeline.py::TestFullPipeline::test_route_type_in_response                 PASSED
tests/test_query_pipeline.py::TestFullPipeline::test_cache_hit_false_on_fresh_query         PASSED
tests/test_query_pipeline.py::TestProviderSelection::test_groq_provider_used_by_default     PASSED
tests/test_query_pipeline.py::TestProviderSelection::test_openrouter_provider_selected      PASSED
tests/test_query_pipeline.py::TestProviderSelection::test_openrouter_model_name_in_response PASSED
tests/test_query_pipeline.py::TestRerankerFailure::test_reranker_failure_does_not_break_pipeline PASSED
tests/test_query_pipeline.py::TestRerankerFailure::test_reranker_failure_answer_still_grounded   PASSED
tests/test_query_pipeline.py::TestRerankerFailure::test_reranker_failure_still_returns_sources   PASSED
tests/test_query_pipeline.py::TestGroqFallback::test_groq_failure_triggers_openrouter_fallback   PASSED
tests/test_query_pipeline.py::TestGroqFallback::test_groq_timeout_falls_back_to_openrouter       PASSED
tests/test_query_pipeline.py::TestGroqFallback::test_groq_http_error_falls_back_to_openrouter    PASSED
tests/test_query_pipeline.py::TestEmptyRetrieval::test_empty_retrieval_returns_200               PASSED
tests/test_query_pipeline.py::TestEmptyRetrieval::test_empty_retrieval_informative_message       PASSED
tests/test_query_pipeline.py::TestRerankerTopK::test_reranker_called_with_candidates_and_returns_correct_sources PASSED
tests/test_query_pipeline.py::TestInputValidation::test_empty_query_rejected                     PASSED
tests/test_query_pipeline.py::TestInputValidation::test_missing_auth_rejected                    PASSED

21 passed in ~8s
```

**Overall after Day 5:** `84 passed, 1 error` (the 1 error is `test_ade.py::test_parse_sample` — a pre-existing fixture issue unrelated to Day 5, present since Day 2).

### 5.2 Ask a Question — Full Answer (Frontend)

1. Make sure a document is uploaded and `completed`
2. Navigate to **💬 Ask a Question**
3. Select a model from the dropdown:
   - **⚡ Groq — Qwen 3.8 27B** (default, faster)
   - **🔮 OpenRouter — Nemotron 120B** (larger, free tier)
4. Type your question and click **🔍 Ask Question**

**Expected results panel (Day 5 — real answer):**

```
📝 Text  ⚡ Groq  qwen/qwen3.8-27b  560 tokens  $0.0003   ⏱ 2850 ms   5 sources
┌─────────────────────────────────────────────────────────────────────┐
│ Total revenue in Q3 was $4.2 billion, representing a 12% increase  │
│ year-over-year. [Source 1] The breakdown by segment shows...       │
│ [Source 2]                                                          │
└─────────────────────────────────────────────────────────────────────┘
📎 Sources  grounded citations — sorted by relevance
  #1  📁 report.pdf  📄 Text   Page 3   94.5%  ▼
  #2  📁 report.pdf  📊 Table  Page 5   89.1%  ▼
  ...
```

**Answer box:** Now shows the real LLM answer (no placeholder badge).

**Model badge (green pill):**
```
⚡ Groq  qwen/qwen3.8-27b  560 tokens  $0.0003
```

**Source card (expanded):**
```
"Q3 net revenue reached $4.2 billion, representing..."

Chunk ID   abc12345678...
Doc ID     sha256abc12...
BBox       [0.14, 0.07, 0.85, 0.11]
```

**Note:** Filename now appears in source card headers (📁 report.pdf).

### 5.3 Switch Provider to Nemotron 120B

1. In the query form, open the **🤖 Model** dropdown
2. Select **🔮 OpenRouter — Nemotron 120B**
3. Ask the same question

**Expected:**
- Model badge shows: `🔮 OpenRouter  nvidia/nemotron-3-super-120b-a12b:free`
- `cost_usd` shows `$0.0000` (free tier)
- Answer may be slightly different phrasing — same grounded content

### 5.4 Debug Panel — Full Pipeline Latency

After receiving a result, click **🔓 Show debug**.

**Expected debug panel (Day 5 — all stages filled):**
```
🔬 Pipeline Debug
Embed: 1198 ms  |  Retrieve: 44 ms  |  Rerank: 380 ms  |  LLM: 1228 ms  |  Route: text

Input tokens: 512   Output tokens: 48   Total tokens: 560
```

> [!NOTE]
> In Day 4, `Rerank` and `LLM` were `0 ms`. Now all four stages show real timings.

### 5.5 API Test via Swagger (`POST /query`) — Day 5

Go to **http://localhost:8000/docs** → Authorize with JWT.

**Request with provider selection:**
```json
{
  "query": "What is the total revenue?",
  "llm_provider": "groq"
}
```

**Request forcing OpenRouter:**
```json
{
  "query": "Show me the revenue table",
  "llm_provider": "openrouter"
}
```

**Expected 200 response (Day 5):**
```json
{
  "answer": "Total revenue in Q3 was $4.2 billion based on the provided evidence. [Source 1] The sales breakdown shows... [Source 2]",
  "sources": [
    {
      "document_id": "abc123...",
      "chunk_id": "sha256...",
      "page": 2,
      "bbox": [0.14, 0.07, 0.85, 0.11],
      "chunk_type": "text",
      "text_preview": "Q3 net revenue reached $4.2 billion...",
      "relevance_score": 0.945,
      "filename": "budget_report.pdf"
    }
  ],
  "route_type": "text",
  "cache_hit": false,
  "model_used": "qwen/qwen3.8-27b",
  "provider_used": "groq",
  "latency": {
    "total_ms": 2850.2,
    "cache_check_ms": 0.0,
    "query_embed_ms": 1198.4,
    "retrieval_ms": 44.2,
    "reranking_ms": 380.1,
    "llm_ms": 1227.5
  },
  "token_usage": {
    "input_tokens": 512,
    "output_tokens": 48,
    "total_tokens": 560
  },
  "cost_usd": 0.0003
}
```

**Key differences from Day 4:**

| Field | Day 4 | Day 5 |
|---|---|---|
| `answer` | Placeholder text | Real grounded LLM answer with `[Source N]` citations |
| `model_used` | `""` (empty) | `"qwen/qwen3.8-27b"` |
| `provider_used` | `""` (empty) | `"groq"` |
| `latency.reranking_ms` | `0.0` | `~380 ms` |
| `latency.llm_ms` | `0.0` | `~1200 ms` |
| `token_usage` | `{}` (empty) | `{ input_tokens, output_tokens, total_tokens }` |
| `cost_usd` | `0.0` | `~0.0003` |
| `sources[*].filename` | `""` (empty) | `"budget_report.pdf"` |
| `sources` count | Up to 20 (raw retrieval) | Up to 5 (post-rerank) |

### 5.6 PowerShell Verification Commands

```powershell
# Get token
$loginResult = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
  -Method POST -ContentType "application/x-www-form-urlencoded" `
  -Body "username=yourusername&password=yourpassword"
$token = $loginResult.access_token

# Full pipeline — Groq primary
$result = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/query" `
  -Method POST `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body '{"query": "What is the total revenue?", "llm_provider": "groq"}'

# Inspect the answer
$result.answer

# Inspect provider + model
$result | Select-Object provider_used, model_used, cost_usd

# Inspect full latency breakdown
$result.latency

# Inspect token usage
$result.token_usage

# Count sources (should be ≤ 5 after reranking)
$result.sources.Count

# Check first source filename is populated
$result.sources[0].filename

# Force OpenRouter Nemotron 120B
$result2 = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/query" `
  -Method POST `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body '{"query": "What is the total revenue?", "llm_provider": "openrouter"}'
$result2 | Select-Object provider_used, model_used, cost_usd
```

**Expected outputs:**
```
# $result.answer
"Total revenue in Q3 was $4.2 billion based on the evidence. [Source 1]..."

# provider + model
provider_used  model_used           cost_usd
-------------- -------------------- --------
groq           qwen/qwen3.8-27b     0.0003

# latency
total_ms       : 2850.2
cache_check_ms : 0.0
query_embed_ms : 1198.4
retrieval_ms   : 44.2
reranking_ms   : 380.1
llm_ms         : 1227.5

# token_usage
input_tokens  : 512
output_tokens : 48
total_tokens  : 560

# source count
5

# filename
budget_report.pdf

# OpenRouter result
provider_used       model_used                              cost_usd
-----------         ---------------------------------------  --------
openrouter          nvidia/nemotron-3-super-120b-a12b:free  0.0
```

### 5.7 Log Reading Guide — Day 5 Full Pipeline

Full structured log for one complete query (all stages):

```
INFO  Query pipeline started
      user_id=u123  query_preview="What is the total revenue?"
      preferred_provider=groq  top_n=20  top_k=5

# Step 1: Route (< 1 ms)
INFO  Query routed           route=text

# Step 2: Embed query (~1–2 sec)
DEBUG Calling OpenRouter embeddings API  input_type=query
INFO  Embedding batch complete           latency_ms=1198.4  total_tokens=8
INFO  Query embedded                     embed_ms=1198.4

# Step 3: Retrieve Top-20 (~40–80 ms)
INFO  Retrieval complete     strategy=text  results_count=20  latency_ms=44.2

# Step 4: Rerank Top-5 (~300–600 ms)
INFO  Calling OpenRouter reranker   model=nvidia/llama-nemotron-rerank-vl-1b-v2:free
                                    candidates_count=20  top_k=5
INFO  Reranking complete            latency_ms=380.1  returned=5

# Step 5: Context assembly
INFO  Context assembled       chunks_selected=5  tokens_est=1240  truncated=False

# Step 6: Generate (Groq, ~800–2000 ms)
INFO  Calling primary LLM (Groq)   model=qwen/qwen3.8-27b
INFO  Groq generation complete     input_tokens=512  output_tokens=48  latency_ms=1227.5  cost_usd=0.0003

# Pipeline complete
INFO  Query pipeline complete
      route=text  provider=groq  model=qwen/qwen3.8-27b
      fallback=False  rerank_skipped=False
      total_ms=2850.2  llm_ms=1227.5  total_tokens=560  cost_usd=0.0003
```

### 5.8 Reranker Failure — Log Observation

If the OpenRouter reranker is unavailable (e.g. API key quota exceeded):

```
INFO  Calling OpenRouter reranker   candidates_count=20  top_k=5
ERROR Reranker failed — skipping reranking, using raw retrieval order
      error=HTTPStatusError  error_type=httpx.HTTPStatusError

# Pipeline continues — LLM still generates answer from raw Top-5
INFO  Context assembled       chunks_selected=5  tokens_est=1100  truncated=False
INFO  Calling primary LLM (Groq)
INFO  Query pipeline complete  rerank_skipped=True
```

> [!NOTE]
> `rerank_skipped=True` in the log tells you reranking was bypassed.
> The answer is still generated — just from retrieval order, not reranked order.

### 5.9 Groq Fallback — Log Observation

If Groq fails (rate limit, bad API key, timeout):

```
INFO  Calling primary LLM (Groq)
WARNING  Groq failed — triggering OpenRouter fallback
         fallback_reason=HTTPStatusError: 429 Too Many Requests

INFO  Calling OpenRouter fallback LLM (Nemotron 120B)
INFO  OpenRouter LLM succeeded   provider=openrouter  fallback=True
INFO  Query pipeline complete    provider=openrouter  model=nvidia/nemotron-3-super-120b-a12b:free
                                  fallback_triggered=True
```

> [!NOTE]
> The response still returns `200 OK` with a real answer — just from OpenRouter instead of Groq.
> `provider_used` in the response will be `"openrouter"` instead of `"groq"`.

### 5.10 Error Cases

| Test | Expected |
|------|----------|
| No `Authorization` header | `401 Unauthorized` |
| Empty `query` string | `422 Unprocessable Entity` |
| Both Groq AND OpenRouter fail | `502 Bad Gateway` with `LLM generation failed` detail |
| Valid query, empty ChromaDB | `200` with informative `answer`, `sources: []` |
| `llm_provider` = `"groq"` (default) | `provider_used: "groq"` in response |
| `llm_provider` = `"openrouter"` | `provider_used: "openrouter"`, Groq skipped entirely |
| Reranker fails mid-pipeline | `200` with answer from raw retrieval order |

---

## Day 6 — Redis Query-Answer Cache

> [!IMPORTANT]
> **What Day 6 added:** Every answer coming out of the full LLM pipeline is now cached in Redis
> (Upstash) as a Hash. On the **next identical query** from the same user, the pipeline is skipped
> entirely and the answer is returned directly from Redis — typical latency drops from ~3 s to ~30 ms.
>
> - **Cache check** happens before Step 1 (routing). Cache hit → instant return.
> - **Cache store** happens after Step 6 (LLM generation). Fresh answer → written to Redis.
> - **Cache invalidation** fires when a document is re-ingested — stale answers are deleted first.
> - **Graceful degradation:** if Redis is down, the pipeline runs normally. No crash, no 500.
> - **New endpoint:** `GET /query/history` — list all cached Q&A pairs for the logged-in user.

---

### Why Redis? Why a Hash? Why TTL?

| Question | Answer |
|---|---|
| **Why Redis?** | Sub-millisecond reads. The embedding + rerank + LLM pipeline takes 2–4 s per query. Caching makes repeat queries feel instant. |
| **Why a Hash?** | One Hash key per user+document holds *all* their questions as fields. Efficient — one `HGET` per query lookup, one `HGETALL` for history. |
| **Why SHA-256 for field names?** | Normalises casing and whitespace (`"Revenue?"` = `"revenue?"`) into a fixed-length key regardless of question length. |
| **Why TTL on the whole key?** | Redis only supports TTL on keys, not individual Hash fields. Setting `EXPIRE` on every write gives sliding TTL — the key lives as long as the user stays active. |
| **Why 3600 s (1 hour)?** | Balances freshness vs speed. Configurable via `CACHE_TTL_SECONDS` in `.env`. |

---

### How the Cache Key Is Built

```
KEY    →  user:{user_id}:qa:{doc_key}
FIELD  →  SHA-256( query.lower().strip() )
VALUE  →  QueryResponse JSON (cache_hit stored as false; set to true on read)

Examples:
  user:alice:qa:__all__          ← no document filter (searched all docs)
  user:alice:qa:abc123def456     ← filtered to a single document
  user:bob:qa:__all__            ← separate namespace per user
```

```
Redis Database (Upstash — RAG-qa-store)
│
└── KEY: user:alice:qa:__all__                 TTL: 60 min
    │   Type: HASH  |  Length: N (one field per unique question)
    │
    ├── FIELD: sha256("what is total revenue?")  → { answer, sources, latency, ... }
    ├── FIELD: sha256("show me the table")         → { answer, sources, latency, ... }
    └── FIELD: sha256("who wrote this report?")    → { answer, sources, latency, ... }
```

---

### How the Full Pipeline Changes in Day 6

```
POST /query  →  "What is the total revenue?"
        ↓
[Step 0]  Cache check  →  Redis HGET  (< 30 ms)
          HIT  →  return instantly  ⚡ cache_hit=true  (pipeline ends here)
          MISS →  continue to Step 1
        ↓
[Step 1]  Route   →  text
[Step 2]  Embed   →  NVIDIA Nemotron (~1–2 s)
[Step 3]  Retrieve Top-20  →  ChromaDB (~40 ms)
[Step 4]  Rerank Top-5  →  NVIDIA Reranker (~380 ms)
[Step 5]  Assemble context  →  token-budgeted grounded prompt
[Step 6]  Generate  →  Groq Qwen 3.8 27B (~1.2 s)
        ↓
[Step 7]  Cache store  →  Redis HSET + EXPIRE  (async, < 5 ms)
        ↓
        Return  QueryResponse  cache_hit=false
```

---

### 6.1 Automated Tests

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend

# Day 6 cache unit tests only (17 tests, all mocked, < 10s)
.venv\Scripts\python.exe -m pytest tests/test_cache.py -v

# Full suite Days 0–6 (101 pass, 1 pre-existing ADE fixture error)
.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_redis.py -v
```

**Expected Day 6 cache test output:**
```
tests/test_cache.py::test_cache_key_format                              PASSED
tests/test_cache.py::test_cache_key_all_docs                            PASSED
tests/test_cache.py::test_field_key_normalisation                       PASSED
tests/test_cache.py::test_doc_key_none_returns_all                      PASSED
tests/test_cache.py::test_doc_key_single_doc                            PASSED
tests/test_cache.py::test_doc_key_multi_docs_returns_all                PASSED
tests/test_cache.py::test_cache_miss_returns_none                       PASSED
tests/test_cache.py::test_cache_hit_returns_response                    PASSED
tests/test_cache.py::test_cache_hit_stamps_cache_hit_true               PASSED
tests/test_cache.py::test_cache_set_stores_response                     PASSED
tests/test_cache.py::test_cache_set_stored_value_has_cache_hit_false    PASSED
tests/test_cache.py::test_cache_invalidation_calls_scan_delete          PASSED
tests/test_cache.py::test_list_user_qa_pairs_returns_all_entries        PASSED
tests/test_cache.py::test_list_user_qa_pairs_empty_when_no_cache        PASSED
tests/test_cache.py::test_get_cached_response_degrades_gracefully       PASSED
tests/test_cache.py::test_set_cached_response_degrades_gracefully       PASSED
tests/test_cache.py::test_invalidate_document_cache_degrades_gracefully PASSED

17 passed in < 10s
```

**Overall after Day 6:** `101 passed, 1 error` (the 1 error is `test_ade.py::test_parse_sample` — pre-existing fixture issue since Day 2, unrelated to Day 6).

### 6.2 Ask a Question — Cache Miss (First Query)

1. Start backend and frontend (same commands as Days 0–5)
2. Log in at **http://localhost:5173**
3. Navigate to **💬 Ask a Question**
4. Type a question and click **🔍 Ask Question**

**Expected on first query (cache miss):**

```
📝 Text  ⚡ Groq  qwen/qwen3.8-27b  560 tokens  $0.0003   ⏱ 2850 ms   5 sources
┌─────────────────────────────────────────────────────────────────────┐
│ Total revenue in Q3 was $4.2 billion... [Source 1]                  │
└─────────────────────────────────────────────────────────────────────┘
```

- No ⚡ badge → fresh pipeline run
- `cache_hit: false` in the JSON response
- Backend logs show all 7 steps

**Backend log — cache miss:**
```
INFO  Query pipeline started    user_id=alice  query_preview="What is the total revenue?"
INFO  Cache miss                cache_check_ms=28.0
INFO  Query routed              route=text
... (embed → retrieve → rerank → assemble → generate) ...
INFO  Groq generation complete  latency_ms=1227.5
INFO  Cache stored              doc_key=__all__
INFO  Query pipeline complete   total_ms=2850.2
```

### 6.3 Ask the Same Question Again — Cache Hit

Ask the exact same question (same wording, any casing — `"Revenue?"` = `"revenue?"`).

**Expected on second query (cache hit):**

```
⚡ Instant (cached)   📝 Text   ⏱ 31 ms   5 sources
┌─────────────────────────────────────────────────────────────────────┐
│ Total revenue in Q3 was $4.2 billion... [Source 1]                  │
└─────────────────────────────────────────────────────────────────────┘
```

- **⚡ Instant (cached)** amber badge appears with a pulse animation
- Total latency drops from ~2850 ms → ~31 ms
- `cache_hit: true` in the JSON response
- Pipeline steps 1–6 are skipped entirely

**Backend log — cache hit:**
```
INFO  Query pipeline started    user_id=alice  query_preview="What is the total revenue?"
INFO  Cache HIT                 doc_key=__all__
INFO  Serving from cache        cache_check_ms=31.0
```

> [!TIP]
> The ⚡ badge has a one-shot amber pulse animation on appearance so it's immediately
> obvious that this result came from cache, not a fresh pipeline run.

### 6.4 Cache Invalidation — Re-upload a Document

Re-upload any document that was previously queried.

**Expected backend log during re-ingestion:**
```
INFO  Cache invalidated   document_id=abc123  keys_deleted=1
INFO  Ingestion started   status=processing
```

After re-ingestion completes, asking the same question again will be a **cache miss** — the pipeline runs fresh and the new chunks are used.

> [!IMPORTANT]
> Invalidation fires **before** new chunks are written to ChromaDB. This ensures no
> stale cached answer is ever served while new content is being indexed.

### 6.5 API — Cache Hit Response vs Miss Response

**First call (miss):**
```json
{
  "answer": "Total revenue in Q3 was $4.2 billion... [Source 1]",
  "cache_hit": false,
  "latency": {
    "total_ms": 2850.2,
    "cache_check_ms": 28.0,
    "query_embed_ms": 1198.4,
    "retrieval_ms": 44.2,
    "reranking_ms": 380.1,
    "llm_ms": 1227.5
  },
  "model_used": "qwen/qwen3.8-27b",
  "provider_used": "groq"
}
```

**Second call (hit):**
```json
{
  "answer": "Total revenue in Q3 was $4.2 billion... [Source 1]",
  "cache_hit": true,
  "latency": {
    "total_ms": 31.0,
    "cache_check_ms": 31.0,
    "query_embed_ms": 0.0,
    "retrieval_ms": 0.0,
    "reranking_ms": 0.0,
    "llm_ms": 0.0
  },
  "model_used": "qwen/qwen3.8-27b",
  "provider_used": "groq"
}
```

**Key differences:**

| Field | Miss | Hit |
|---|---|---|
| `cache_hit` | `false` | `true` |
| `latency.total_ms` | ~2850 ms | ~31 ms |
| `latency.cache_check_ms` | ~28 ms | ~31 ms |
| `latency.query_embed_ms` | ~1198 ms | `0.0` |
| `latency.llm_ms` | ~1228 ms | `0.0` |
| Frontend badge | *(none)* | ⚡ Instant (cached) |

### 6.6 API — Query History Endpoint

```powershell
# Get token
$loginResult = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
  -Method POST -ContentType "application/x-www-form-urlencoded" `
  -Body "username=yourusername&password=yourpassword"
$token = $loginResult.access_token

# List all cached Q&A pairs for this user (all documents)
$history = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/query/history" `
  -Headers @{ Authorization = "Bearer $token" }
$history.Count
$history[0].response.answer

# Filter to a specific document
$history2 = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/v1/query/history?document_id=<doc_id>" `
  -Headers @{ Authorization = "Bearer $token" }
```

**Expected response shape:**
```json
[
  {
    "field_key": "fde76c309ea5ba6fb7ccb2b04e11ee7f...",
    "response": {
      "answer": "Total revenue was $100M...",
      "cache_hit": false,
      "model_used": "qwen/qwen3.8-27b",
      "provider_used": "groq",
      "latency": { ... },
      "sources": [ ... ]
    }
  }
]
```

> [!NOTE]
> `field_key` is the SHA-256 fingerprint of the original query.
> If the user has asked 3 questions, the list will have 3 entries.
> Returns `[]` if Redis is down (graceful degradation).

### 6.7 Swagger (`GET /query/history`)

1. Go to **http://localhost:8000/docs**
2. Authorize with JWT
3. Find `GET /api/v1/query/history`
4. Execute with no params → returns all cached pairs
5. Execute with `document_id=<id>` → returns only pairs for that document

### 6.8 PowerShell Verification Commands

```powershell
# Get token
$loginResult = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
  -Method POST -ContentType "application/x-www-form-urlencoded" `
  -Body "username=yourusername&password=yourpassword"
$token = $loginResult.access_token

# First query — expect cache_hit=false, latency ~2850 ms
$r1 = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/query" `
  -Method POST `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body '{"query": "What is the total revenue?"}'
$r1 | Select-Object cache_hit, @{n="total_ms";e={$_.latency.total_ms}}

# Same query again — expect cache_hit=true, latency ~30 ms
$r2 = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/query" `
  -Method POST `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body '{"query": "What is the total revenue?"}'
$r2 | Select-Object cache_hit, @{n="total_ms";e={$_.latency.total_ms}}

# History — count cached Q&A pairs
$h = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/query/history" `
  -Headers @{ Authorization = "Bearer $token" }
"Cached pairs: $($h.Count)"
```

**Expected outputs:**
```
# First call
cache_hit  total_ms
---------  --------
False      2850.2

# Second call (cache hit)
cache_hit  total_ms
---------  --------
True       31.0

# History
Cached pairs: 1
```

### 6.9 Reading the Cache in Upstash Data Browser

Open your Upstash console → **Data Browser** tab.

```
Key:   user:alice:qa:__all__
Type:  HASH
TTL:   52m 12s              ← auto-expires, no manual cleanup needed
Size:  1.2 KB
Length: 1                   ← number of cached Q&A pairs

Field  →  fde76c309ea5ba6fb7ccb2b04e11ee7f...   (SHA-256 of query)
Value  →  {"answer":"Total revenue was $100M...", ...}
```

> [!NOTE]
> TTL resets to 1 hour every time a new answer is cached under that key.
> After 1 hour of inactivity, the entire key expires automatically.

### 6.10 Log Reading Guide — Day 6 Cache Pipeline

**Full log for cache miss (pipeline runs):**
```
INFO  Query pipeline started     user_id=alice  query_preview="What is the total revenue?"

# Step 0: Cache check (~28 ms)
INFO  Cache MISS                 doc_key=__all__
INFO  Cache miss                 cache_check_ms=28.0

# Steps 1–6: Full pipeline (same as Day 5)
INFO  Query routed               route=text
INFO  Query embedded             embed_ms=1198.4
INFO  Retrieval complete         results_count=20
INFO  Reranking complete         returned=5
INFO  Context assembled          chunks_selected=5
INFO  Groq generation complete   latency_ms=1227.5

# Step 7: Cache store (~3 ms)
INFO  Cache stored               doc_key=__all__  ttl_s=3600

INFO  Query pipeline complete    total_ms=2850.2  cache_hit=False
```

**Full log for cache hit (pipeline skipped):**
```
INFO  Query pipeline started     user_id=alice  query_preview="What is the total revenue?"

# Step 0: Cache HIT (~31 ms)
INFO  Cache HIT                  doc_key=__all__
INFO  Serving from cache         cache_check_ms=31.0

# Steps 1–7 are completely skipped
INFO  HTTP request               status_code=200  latency_ms=31.0
```

**Cache invalidation log (during re-ingestion):**
```
INFO  Cache invalidated          document_id=abc123  keys_deleted=1
INFO  Ingestion started          status=processing
```

### 6.11 Error Cases

| Test | Expected |
|---|---|
| No `Authorization` header on `/query/history` | `401 Unauthorized` |
| Redis is down / unreachable | Cache silently skipped — full pipeline runs, `200 OK` returned |
| Redis down during invalidation | `keys_deleted=0` logged, ingestion continues normally |
| Same query, different user | Different Hash key — no cross-user cache leakage |
| Same query, different document filter | Different Hash key (`qa:doc_abc` vs `qa:__all__`) — separate cache entries |
| Ask after TTL expires (>1 hour) | Cache miss — pipeline runs fresh |

---

## Day 7 — Telemetry + SQLite Persistence + Metrics Dashboard

> [!IMPORTANT]
> **What Day 7 added:** All pipeline telemetry is now captured automatically and persisted.
> The in-memory `DocumentStore` / `JobStore` are replaced by **SQLite** (`data/rag.db`) — job and document state now survive server restarts.
> Every query and ingestion appends a `TelemetryRecord` to `data/telemetry.jsonl` covering 5 benchmark categories:
> **Latency** (avg + p95, per-stage) · **Token usage** · **ADE credits** · **Embedding cost** · **LLM cost**.
> A new `GET /metrics` endpoint (no auth) and a frontend **📊 Metrics** dashboard display live aggregated stats.

---

### How the Day 7 Telemetry Pipeline Works

```
POST /query  (or ingestion background task)
        ↓
[All pipeline stages run as normal]
        ↓
[Step 8]  Append TelemetryRecord  →  data/telemetry.jsonl  (async, fire-and-forget)
          TelemetryRecord {
            record_type: "query"  |  "ingestion"
            latency: { total_ms, embedding_ms, retrieval_ms, reranking_ms, llm_ms, ade_ms }
            token_usage: { input_tokens, output_tokens, total_tokens }
            ade_credits: { per_ingestion }
            embedding_cost: { model, provider, token_count, cost_usd }
            llm_cost: { model, provider, input_tokens, output_tokens, cost_usd }
          }
        ↓
GET /api/v1/metrics  →  Reads last 5000 records from telemetry.jsonl
                         Computes: avg latency, p95 latency, cache hit rate,
                                   total tokens, total cost, total ADE credits
```

### SQLite Persistence

```
data/rag.db
│
├── documents   ← DocumentMetadata (replaces in-memory DocumentStore)
│   └── document_id, user_id, filename, status, chunk_count,
│       parser_version, ade_credits_used, embedding_model, ...
│
└── jobs        ← Job records (replaces in-memory JobStore)
    └── job_id, document_id, status, progress_message,
        chunks_created, chunks_embedded, started_at, completed_at, ...
```

> [!NOTE]
> Document and job records now persist across server restarts. On startup, `init_sqlite()` creates
> tables and indexes automatically. The DB file lives at `data/rag.db` (gitignored).

---

### 7.1 Automated Tests

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend

# Day 7 telemetry tests only (19 tests, all async, ~10s)
.venv\Scripts\python.exe -m pytest tests/test_telemetry.py -v

# Full suite Days 0–7 (120 pass, 1 pre-existing ADE fixture error)
.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_ade.py -v
```

**Expected Day 7 test output:**
```
tests/test_telemetry.py::TestTelemetrySchema::test_query_record_has_all_5_categories          PASSED
tests/test_telemetry.py::TestTelemetrySchema::test_ingestion_record_has_all_5_categories      PASSED
tests/test_telemetry.py::TestTelemetrySchema::test_record_type_validation                     PASSED
tests/test_telemetry.py::TestTelemetrySchema::test_query_record_serialization_roundtrip       PASSED
tests/test_telemetry.py::TestTelemetryService::test_append_record_writes_jsonl                PASSED
tests/test_telemetry.py::TestTelemetryService::test_append_multiple_records                   PASSED
tests/test_telemetry.py::TestTelemetryService::test_load_records_empty_file                   PASSED
tests/test_telemetry.py::TestTelemetryService::test_load_records_after_append                 PASSED
tests/test_telemetry.py::TestTelemetryService::test_append_error_does_not_raise               PASSED
tests/test_telemetry.py::TestComputeMetrics::test_empty_telemetry_returns_zeros               PASSED
tests/test_telemetry.py::TestComputeMetrics::test_query_count_and_cache_hit_rate              PASSED
tests/test_telemetry.py::TestComputeMetrics::test_avg_latency_computed_correctly              PASSED
tests/test_telemetry.py::TestComputeMetrics::test_p95_latency                                 PASSED
tests/test_telemetry.py::TestComputeMetrics::test_ade_credits_summed_from_ingestion_records   PASSED
tests/test_telemetry.py::TestComputeMetrics::test_total_tokens_and_cost                       PASSED
tests/test_telemetry.py::TestComputeMetrics::test_records_analyzed_field                      PASSED
tests/test_telemetry.py::TestMetricsEndpoint::test_get_metrics_returns_200                    PASSED
tests/test_telemetry.py::TestMetricsEndpoint::test_get_metrics_no_auth_required               PASSED
tests/test_telemetry.py::TestMetricsEndpoint::test_get_metrics_with_real_data                 PASSED

19 passed in ~10s
```

**Overall after Day 7:** `120 passed, 1 error` (the 1 error is `test_ade.py::test_parse_sample` — pre-existing fixture issue since Day 2, unrelated to Day 7).

### 7.2 Clean Start — Fresh Data Directory

Since SQLite replaces the in-memory store and everything starts fresh, clean the old data:

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend
Remove-Item -Recurse -Force data\chroma, data\uploads, data\ade_outputs, data\telemetry.jsonl, data\rag.db -ErrorAction SilentlyContinue
```

**Expected server startup logs (Day 7):**
```
INFO  Starting Multimodal RAG API    version=0.1.0
INFO  ChromaDB initialized           collection=ade_documents  existing_chunks=0
INFO  SQLite store initialised       db_path=data/rag.db
INFO  Redis connected successfully
INFO  All services initialized. Ready to serve.
```

> [!NOTE]
> `SQLite store initialised` is the new line added in Day 7. The `data/rag.db` file is created
> automatically on first startup. Documents and jobs uploaded before this restart are gone
> (fresh start), but after this the state is durable across restarts.

### 7.3 Upload a Document — Verify SQLite Persistence

1. Upload any PDF and wait for `completed` status
2. Restart the backend server (Ctrl+C → restart)
3. Navigate to **📁 Documents** — the document should still appear as `completed`

**Before Day 7:** Document disappeared on restart (in-memory).
**After Day 7:** Document persists in `data/rag.db` — survives server restarts.

Verify the SQLite DB directly:

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend
.venv\Scripts\python.exe -c "
import asyncio, aiosqlite
async def check():
    async with aiosqlite.connect('data/rag.db') as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute('SELECT document_id, filename, status, chunk_count FROM documents')
        rows = await cur.fetchall()
        for r in rows: print(dict(r))
asyncio.run(check())
"
```

**Expected output:**
```
{'document_id': 'sha256abc...', 'filename': 'budget_report.pdf', 'status': 'completed', 'chunk_count': 4}
```

### 7.4 Run Queries — Verify Telemetry Records

1. Ask a question (cache miss — full pipeline runs)
2. Check that `data/telemetry.jsonl` was created:

```powershell
Get-Content "data\telemetry.jsonl" | ConvertFrom-Json | Select-Object record_type, @{n="total_ms";e={$_.latency.total_ms}}, @{n="provider";e={$_.llm_cost.provider}}
```

**Expected output:**
```
record_type  total_ms  provider
-----------  --------  --------
query        2850.2    groq
```

After uploading another document, an ingestion record is also appended:
```
record_type  total_ms  provider
-----------  --------  --------
query        2850.2    groq
ingestion    5200.0
```

### 7.5 GET /metrics — API Response

**No auth required.**

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/metrics" | ConvertTo-Json -Depth 5
```

**Expected 200 response:**
```json
{
  "query_count": 3,
  "ingestion_count": 1,
  "cache_hit_count": 1,
  "cache_hit_rate": 0.3333,
  "avg_latency_ms": 2840.5,
  "p95_latency_ms": 3012.1,
  "latency_by_stage": {
    "embedding_ms": 1198.0,
    "retrieval_ms": 44.2,
    "reranking_ms": 381.0,
    "llm_ms": 1217.3,
    "ade_ms": 4500.0
  },
  "total_tokens": 1680,
  "total_cost_usd": 0.000900,
  "total_embedding_cost_usd": 0.0,
  "total_llm_cost_usd": 0.000900,
  "total_ade_credits": 3.0,
  "records_analyzed": 4,
  "oldest_record_ts": "2026-10-02T06:50:00+00:00",
  "newest_record_ts": "2026-10-02T07:12:43+00:00"
}
```

**Key fields:**

| Field | Description |
|---|---|
| `query_count` | Total queries run through the pipeline |
| `cache_hit_rate` | Fraction of queries served from Redis cache |
| `avg_latency_ms` | Mean end-to-end latency (query records only) |
| `p95_latency_ms` | 95th-percentile latency |
| `latency_by_stage` | Average per stage: embed, retrieve, rerank, LLM, ADE |
| `total_tokens` | Input + output tokens summed across all queries |
| `total_cost_usd` | Embedding + LLM costs (USD) |
| `total_ade_credits` | Credits consumed by all ingestion jobs |
| `records_analyzed` | Number of telemetry records read from `telemetry.jsonl` |

### 7.6 Frontend — Metrics Dashboard

1. Log in at **http://localhost:5173**
2. Click **📊 Metrics** in the navbar

**Expected dashboard sections:**

**Overview:**
```
🔍 Total Queries     ⚡ Cache Hit Rate    📄 Records Analysed
   3                    33.3%               4
   1 ingestions          1 hits             Since 2026-10-02
```

**Latency:**
```
⏱ Avg End-to-End     📈 p95 Latency
  2.84 s               3.01 s

Avg per-stage breakdown (query records)
  🔢 Embedding  ████████████░░░░  1198 ms
  🔍 Retrieval  █░░░░░░░░░░░░░░░  44 ms
  🏆 Reranking  ████░░░░░░░░░░░░  381 ms
  🤖 LLM        ████████████████  1217 ms
  📑 ADE        ░░░░░░░░░░░░░░░░  0 ms  (ingestion only)
```

**Cost & Usage:**
```
🪙 Total LLM Cost    🧮 Embedding Cost    💰 Total Cost    📝 Total Tokens
  $0.000900            $0.000000           $0.000900        1,680
```

**ADE Credits:**
```
🏦 Total ADE Credits Used
   3.00
   Across 1 ingestion(s)
```

> [!TIP]
> The dashboard **auto-refreshes every 30 seconds**. Click **↻ Refresh** to force an immediate update.
> The last refresh time is shown in the top-right corner.

### 7.7 Frontend — Performance Details Panel (QueryPage)

After every query result, a new **⚙️ Performance Details** collapsible panel appears below the answer:

1. Click **⚙️ Performance Details** to expand
2. **Expected panel contents:**

```
⚙️ Performance Details                    2850 ms total  ▼
┌───────────────────────────────────────────────────────────┐
│ ⏱ Latency Breakdown                                       │
│   🔢 Embedding  ████████████░  1198 ms                    │
│   🔍 Retrieval  █░░░░░░░░░░░░  44 ms                      │
│   🏆 Reranking  ████░░░░░░░░░  380 ms                     │
│   🤖 LLM        ██████████████  1227 ms                   │
│                                                           │
│ 🔤 Token Usage                                            │
│      512          48         560                          │
│     Input       Output       Total                        │
│                                                           │
│ 💰 Estimated Cost                                         │
│   $0.000300                                               │
└───────────────────────────────────────────────────────────┘
```

### 7.8 PowerShell Verification Commands

```powershell
# Get metrics (no auth required)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/metrics" | Select-Object query_count, cache_hit_rate, avg_latency_ms, total_cost_usd, total_ade_credits

# Tail telemetry.jsonl (last 3 records)
$lines = Get-Content "data\telemetry.jsonl"
$lines | Select-Object -Last 3 | ForEach-Object { $_ | ConvertFrom-Json | Select-Object record_type, @{n="total_ms";e={$_.latency.total_ms}} }

# Verify SQLite has documents
.venv\Scripts\python.exe -c "
import asyncio, aiosqlite
async def q():
    async with aiosqlite.connect('data/rag.db') as db:
        cur = await db.execute('SELECT COUNT(*) FROM documents')
        print('Documents in SQLite:', (await cur.fetchone())[0])
        cur2 = await db.execute('SELECT COUNT(*) FROM jobs')
        print('Jobs in SQLite:', (await cur2.fetchone())[0])
asyncio.run(q())
"
```

**Expected outputs:**
```
# Metrics
query_count  cache_hit_rate  avg_latency_ms  total_cost_usd  total_ade_credits
-----------  --------------  --------------  --------------  -----------------
3            0.3333          2840.5          0.000900        3.0

# Telemetry tail
record_type  total_ms
-----------  --------
query        2850.2
query        31.0
ingestion    5200.0

# SQLite counts
Documents in SQLite: 2
Jobs in SQLite: 2
```

### 7.9 Log Reading Guide — Day 7 Telemetry

**Telemetry append on query completion:**
```
INFO  Query pipeline complete
      route=text  provider=groq  total_ms=2850.2  cost_usd=0.0003

# (immediately after — fire-and-forget, non-blocking)
DEBUG Telemetry record appended  record_type=query  record_id=uuid...
```

**Telemetry append on ingestion completion:**
```
INFO  Ingestion completed        status=completed  chunk_count=4
DEBUG Telemetry record appended  record_type=ingestion  record_id=uuid...
```

**Telemetry write failure (non-fatal):**
```
WARNING Telemetry append failed (non-fatal)  error=disk full  record_id=uuid...
# Pipeline continues normally — telemetry failure NEVER breaks the API
```

**SQLite init on startup:**
```
INFO  SQLite store initialised  db_path=data/rag.db
```

### 7.10 Error Cases

| Test | Expected |
|---|---|
| `GET /metrics` with no auth | `200 OK` — no auth required |
| `GET /metrics` with empty `telemetry.jsonl` | `200 OK` with all zeros |
| `telemetry.jsonl` write fails (disk full) | Warning logged, pipeline returns `200 OK` normally |
| Server restart after documents uploaded | Documents still visible — persisted in `data/rag.db` |
| `data/rag.db` deleted manually | Tables recreated on next startup — documents/jobs lost (fresh start) |
| Metrics with only ingestion records | `query_count=0`, `avg_latency_ms=0`, `total_ade_credits` populated |
| Metrics with only query records | `ingestion_count=0`, `total_ade_credits=0`, latency computed from queries |

---

## Day 8 — RAG Evaluation & Source Grounding

> [!IMPORTANT]
> **What Day 8 added:** The platform now features a quantitative retrieval evaluation framework and visual citation grounding.
> - **Gold Dataset (`data/gold_dataset.json`):** Ground-truth evaluation dataset mapping benchmark questions to expected document IDs and chunk IDs. Supports automatic, rule-based generation from ingested chunks if a dataset doesn't already exist.
> - **Retrieval Metrics (Recall@K & Precision@K):** Evaluates retrieval effectiveness both **pre-rerank** (raw ChromaDB Top-N) and **post-rerank** (NVIDIA Nemotron reranked Top-K), measuring reranking lift.
> - **Evaluation Endpoint (`GET /api/v1/evaluation/run`):** Open endpoint (no auth required) that runs the evaluation pipeline against the gold dataset and produces aggregate summary metrics and per-question breakdowns.
> - **Evaluation Dashboard (`EvaluationPage.jsx`):** Interactive frontend dashboard with a K-selector (1–10), "Run Evaluation" trigger, aggregate metric cards with improvement badges (▲/▼), and a detailed per-question comparison table.
> - **Visual Source Grounding (`QueryPage.jsx`):** Source citation cards now display an SVG page thumbnail preview showing the normalized ADE bounding box (`[x0, y0, x1, y1]`) highlighted in real time, color-coded according to chunk type (`text`, `table`, or `figure`).

---

### How the Evaluation Pipeline Works

```
Gold Dataset (data/gold_dataset.json)
[ { "question": "...", "expected_document_ids": [...], "expected_chunk_ids": [...] } ]
                          ↓
      For each question in gold dataset:
                          ↓
       1. [Query Router] → Route (text / multimodal / hybrid)
                          ↓
       2. [Query Embed]  → NVIDIA Nemotron Embed (query mode)
                          ↓
       3. [ChromaDB]     → Retrieve Top-N candidate chunks (default N=20)
                          ↓
       4. [Pre-Rerank Evaluation]
          Compute Recall@K and Precision@K on top-K raw candidates
                          ↓
       5. [Reranker]     → NVIDIA Nemotron Rerank (score candidates)
                          ↓
       6. [Post-Rerank Evaluation]
          Compute Recall@K and Precision@K on top-K reranked candidates
                          ↓
       7. Aggregate across all questions:
          Mean Recall@K (pre & post) · Mean Precision@K (pre & post) · Deltas
```

---

### Metrics Explained: Recall@K vs Precision@K

| Metric | Formula | What It Measures | Target |
|---|---|---|---|
| **Recall@K** | $\frac{\lvert \text{Top-K Retrieved} \cap \text{Expected} \rvert}{\lvert \text{Expected} \rvert}$ | Did the retrieval pipeline find all required ground-truth evidence within the top-$K$ results? | High (ideally 1.0 / 100%) |
| **Precision@K** | $\frac{\lvert \text{Top-K Retrieved} \cap \text{Expected} \rvert}{K}$ | What fraction of the top-$K$ returned chunks are actually relevant? (Penalizes irrelevant distractors) | Balanced with context budget |
| **Post-Rerank Delta** | $\text{Post-Rerank Recall@K} - \text{Pre-Rerank Recall@K}$ | Did the NVIDIA reranker push relevant chunks up into the top-$K$ cut-off? | $\ge 0$ (Reranker improves or preserves ranking) |

---

### Gold Dataset Schema & Generation

```json
[
  {
    "question": "What is the budget breakdown in the report?",
    "expected_document_ids": ["9f2c8d7e..."],
    "expected_chunk_ids": ["a1b2c3d4..."]
  }
]
```

> [!NOTE]
> If `data/gold_dataset.json` does not exist, `load_or_generate()` automatically inspects the first 5 ingested documents in `data/ade_outputs/` and extracts table titles, figure captions, or high-density text sentences to construct realistic questions with known ground-truth `chunk_id`s, saving the file for future reproducible test runs.

---

### Visual Source Grounding (BBox Coordinates & Page SVG)

LandingAI ADE outputs normalized bounding boxes `[x0, y0, x1, y1]` where coordinates range between 0.0 and 1.0 relative to page dimensions:
- $x_0$: Left edge fraction
- $y_0$: Top edge fraction
- $x_1$: Right edge fraction
- $y_1$: Bottom edge fraction

In `QueryPage.jsx`, each expanded source card renders an SVG miniature page (100×141 aspect ratio) showing:
- Dark page background (`#1e293b`) with subtle simulated text layout lines
- Bounding box rectangle with SVG coordinates: $X = x_0 \times 100$, $Y = y_0 \times 141$, $W = (x_1 - x_0) \times 100$, $H = (y_1 - y_0) \times 141$
- Distinct color-coding: **Indigo/Blue** for `text`, **Emerald/Green** for `table`, **Amber** for `figure`
- Visual corner anchor handles and exact coordinate string `[x0, y0, x1, y1]`

---

### 8.1 Automated Tests

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend

# Run Day 8 evaluation tests only (26 tests, all unit/mocked, ~3s)
.venv\Scripts\python.exe -m pytest tests/test_evaluation.py -v

# Full test suite Days 0–8 (143 passed, 1 pre-existing failure)
.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_ade.py -v
```

**Expected Day 8 test output:**
```
tests/test_evaluation.py::TestRecallAtK::test_perfect_recall PASSED      [  3%]
tests/test_evaluation.py::TestRecallAtK::test_partial_recall PASSED      [  7%]
tests/test_evaluation.py::TestRecallAtK::test_zero_recall PASSED         [ 11%]
tests/test_evaluation.py::TestRecallAtK::test_empty_expected_returns_zero PASSED [ 15%]
tests/test_evaluation.py::TestRecallAtK::test_k_smaller_than_retrieved PASSED [ 19%]
tests/test_evaluation.py::TestRecallAtK::test_k_equals_one PASSED        [ 23%]
tests/test_evaluation.py::TestRecallAtK::test_k_equals_one_miss PASSED   [ 26%]
tests/test_evaluation.py::TestPrecisionAtK::test_perfect_precision PASSED [ 30%]
tests/test_evaluation.py::TestPrecisionAtK::test_partial_precision PASSED [ 34%]
tests/test_evaluation.py::TestPrecisionAtK::test_zero_precision PASSED   [ 38%]
tests/test_evaluation.py::TestPrecisionAtK::test_k_zero_returns_zero PASSED [ 42%]
tests/test_evaluation.py::TestPrecisionAtK::test_k_equals_one_hit PASSED [ 46%]
tests/test_evaluation.py::TestPrecisionAtK::test_k_equals_one_miss PASSED [ 50%]
tests/test_evaluation.py::TestGoldDatasetHelpers::test_extract_topic_from_plain_text PASSED [ 53%]
tests/test_evaluation.py::TestGoldDatasetHelpers::test_extract_topic_strips_html PASSED [ 57%]
tests/test_evaluation.py::TestGoldDatasetHelpers::test_extract_table_title PASSED [ 61%]
tests/test_evaluation.py::TestGoldDatasetHelpers::test_question_from_text_chunk PASSED [ 65%]
tests/test_evaluation.py::TestGoldDatasetHelpers::test_question_from_table_chunk PASSED [ 69%]
tests/test_evaluation.py::TestGoldDatasetHelpers::test_question_from_figure_chunk PASSED [ 73%]
tests/test_evaluation.py::TestGoldDatasetHelpers::test_question_from_empty_chunk_returns_none PASSED [ 76%]
tests/test_evaluation.py::TestGoldDatasetIO::test_save_and_load PASSED   [ 80%]
tests/test_evaluation.py::TestGoldDatasetIO::test_load_returns_none_if_no_file PASSED [ 84%]
tests/test_evaluation.py::TestEvaluatePipeline::test_evaluate_pipeline_structure PASSED [ 88%]
tests/test_evaluation.py::TestEvaluatePipeline::test_evaluate_pipeline_perfect_hit PASSED [ 92%]
tests/test_evaluation.py::TestEvaluatePipeline::test_evaluate_pipeline_miss PASSED [ 96%]
tests/test_evaluation.py::TestEvaluatePipeline::test_evaluate_pipeline_empty_gold PASSED [100%]

26 passed in ~3s
```

**Overall after Day 8:** `143 passed, 1 pre-existing error` (`test_get_document_returns_metadata`).

---

### 8.2 Inspect / Generate Gold Dataset

Verify the presence and format of `data/gold_dataset.json`:

```powershell
Get-Content "data\gold_dataset.json" | ConvertFrom-Json | Select-Object -First 2 | ConvertTo-Json -Depth 4
```

**Expected output:**
```json
[
  {
    "question": "What is the budget breakdown in the report?",
    "expected_document_ids": [
      "9f2c8d7e..."
    ],
    "expected_chunk_ids": [
      "a1b2c3d4..."
    ]
  },
  {
    "question": "What are the quarterly expenditure totals?",
    "expected_document_ids": [
      "9f2c8d7e..."
    ],
    "expected_chunk_ids": [
      "e5f6a7b8..."
    ]
  }
]
```

---

### 8.3 Run Evaluation via API (`GET /api/v1/evaluation/run`)

**No authentication required** (observability/evaluation tooling).

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/evaluation/run?k=5" | ConvertTo-Json -Depth 5
```

**Expected 200 response:**
```json
{
  "k": 5,
  "questions_evaluated": 2,
  "pre_rerank": {
    "recall_at_k": 1.0,
    "precision_at_k": 0.2
  },
  "post_rerank": {
    "recall_at_k": 1.0,
    "precision_at_k": 0.2
  },
  "per_question": [
    {
      "question": "What is the budget breakdown in the report?",
      "expected_chunk_ids": ["a1b2c3d4..."],
      "pre_rerank": {
        "retrieved_chunk_ids": ["a1b2c3d4...", "b2c3d4e5...", "c3d4e5f6..."],
        "recall_at_k": 1.0,
        "precision_at_k": 0.2
      },
      "post_rerank": {
        "retrieved_chunk_ids": ["a1b2c3d4...", "c3d4e5f6...", "b2c3d4e5..."],
        "recall_at_k": 1.0,
        "precision_at_k": 0.2
      }
    }
  ]
}
```

**Key metric observations:**
- `pre_rerank.recall_at_k`: Fraction of expected chunks found in top-$K$ raw retrieval.
- `post_rerank.recall_at_k`: Fraction of expected chunks retained in top-$K$ after reranking.
- When $K=5$ and 1 ground truth chunk is expected, perfect recall yields $\text{Precision@5} = \frac{1}{5} = 0.20$ (20%).

---

### 8.4 Frontend — Evaluation Dashboard (`EvaluationPage`)

1. Start backend and frontend
2. Navigate to **http://localhost:5173** and log in
3. Click **🎯 Evaluation** in the top navigation bar
4. Select the evaluation cutoff $K$ (e.g. `K = 5`)
5. Click **▶ Run Evaluation**

**Expected Dashboard Display:**

```
🎯 RAG Evaluation
Measure Recall@K and Precision@K before and after reranking on the gold dataset

Evaluate at K = [ 5 ▼ ] (top-5 candidates considered)       [ ▶ Run Evaluation ]

┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│ Questions Evaluated │ │ Pre-Rerank Recall@5 │ │ Post-Rerank Recall@5│ │Post-Rerank Prec@5   │
│         2           │ │        100.0%       │ │   100.0%  ▲ +0.0%   │ │    20.0%            │
│      at K = 5       │ │   Before reranking  │ │   After reranking   │ │   After reranking   │
└─────────────────────┘ └─────────────────────┘ └─────────────────────┘ └─────────────────────┘

📋 Per-Question Breakdown (2 questions)
┌───┬──────────────────────────────────────┬──────────────┬─────────────┬───────────────┬──────────────┐
│ # │ Question                             │ Pre Recall@5 │ Pre Prec@5  │ Post Recall@5 │ Post Prec@5  │
├───┼──────────────────────────────────────┼──────────────┼─────────────┼───────────────┼──────────────┤
│ 1 │ What is the budget breakdown in...   │    100.0%    │    20.0%    │    100.0%     │    20.0%     │
│ 2 │ What are the quarterly expenditure.. │    100.0%    │    20.0%    │    100.0%     │    20.0%     │
└───┴──────────────────────────────────────┴──────────────┴─────────────┴───────────────┴──────────────┘
```

> [!TIP]
> When post-rerank metrics improve over pre-rerank, a green indicator badge `▲` highlights the lift. If metrics stay identical, a neutral `— same` pill is displayed.

---

### 8.5 Frontend — Source Grounding with Visual Bounding Box (`QueryPage`)

1. Navigate to **💬 Ask a Question**
2. Ask any question about an uploaded document (e.g. `What is the budget report about?`)
3. Below the answer, expand any citation card under **📎 Sources**

**Expected Visual Citation Display:**

```
#1  📁 2_table_budget_report.pdf  📊 Table   Page 1   96.7%  ▲
┌────────────────────────────────────────────────────────────────────────┐
│ 📍 Source location on page 1                                           │
│ ┌───────────────────────────┐                                          │
│ │ ───────────────────────── │                                          │
│ │ ┌───────────────────────┐ │  ← Green emerald highlight for Table     │
│ │ │ ■                   ■ │ │  ← Corner positioning handles            │
│ │ │                       │ │                                          │
│ │ │ ■                   ■ │ │                                          │
│ │ └───────────────────────┘ │                                          │
│ │ ───────────────────────── │                                          │
│ └───────────────────────────┘                                          │
│ [0.120, 0.070, 0.860, 0.320]                                           │
│                                                                        │
│ | Department | Q1 ($) | Q2 ($) | Total ($) |                           │
│ | Finance    | 12,000 | 14,500 | 26,500    |                           │
│                                                                        │
│ Chunk ID  sha256abc123...    Doc ID  sha256def456...   BBox [0.120...] │
└────────────────────────────────────────────────────────────────────────┘
```

- **Type-based color accents:**
  - 📄 `text` → Indigo stroke and soft background (`#6366f1`)
  - 📊 `table` → Emerald green stroke and soft background (`#10b981`)
  - 🖼️ `figure` → Amber stroke and soft background (`#f59e0b`)
- Visual mini-page SVG clearly communicates the physical location of the extracted chunk on the original document page.

---

### 8.6 PowerShell Verification Commands

```powershell
# 1. Check ChromaDB chunk count (ensure at least 1 document indexed)
.venv\Scripts\python.exe -c "
from app.db.chromadb_client import get_collection_stats
print('ChromaDB Stats:', get_collection_stats())
"

# 2. Inspect the gold dataset question list
Get-Content "data\gold_dataset.json" | ConvertFrom-Json | Select-Object question, @{n="chunks";e={$_.expected_chunk_ids.Count}}

# 3. Trigger evaluation via API at K=3
$evalResult = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/evaluation/run?k=3"
$evalResult | Select-Object k, questions_evaluated, @{n="pre_recall";e={$_.pre_rerank.recall_at_k}}, @{n="post_recall";e={$_.post_rerank.recall_at_k}}

# 4. Trigger evaluation via API at K=5
$eval5 = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/evaluation/run?k=5"
$eval5 | Select-Object k, questions_evaluated, @{n="pre_recall";e={$_.pre_rerank.recall_at_k}}, @{n="post_recall";e={$_.post_rerank.recall_at_k}}
```

**Expected output:**
```
ChromaDB Stats: {'total_chunks': 3, 'document_breakdown': {'...': 3}}

question                                        chunks
--------                                        ------
What is the budget breakdown in the report?          1
What are the quarterly expenditure totals?           1

k questions_evaluated pre_recall post_recall
- ------------------- ---------- -----------
3                   2        1.0         1.0

k questions_evaluated pre_recall post_recall
- ------------------- ---------- -----------
5                   2        1.0         1.0
```

---

### 8.7 Log Reading Guide — Day 8 Evaluation Run

Structured logs emitted during an evaluation execution:

```
INFO  Starting evaluation       k=5  gold_questions=2
INFO  Query routed              route=multimodal  keyword_hits=['table']  word_count=8
DEBUG Calling OpenRouter embeddings API  input_type=query
INFO  Retrieval complete        strategy=multimodal  results_count=20
INFO  Calling OpenRouter reranker  candidates_count=20  top_k=5
INFO  Reranking complete        latency_ms=382.4  returned=5
INFO  Evaluation complete       k=5  questions=2  pre_recall=1.0  post_recall=1.0
INFO  HTTP request              method=GET  path=/api/v1/evaluation/run?k=5  status_code=200
```

---

### 8.8 Error Cases

| Test | Expected |
|---|---|
| `GET /evaluation/run` with no documents in ChromaDB | `400 Bad Request` with `{"error": "No documents indexed — cannot evaluate"}` |
| `GET /evaluation/run?k=0` or `k=-5` | Clamped to `k=1`, evaluation runs with $K=1$ |
| `GET /evaluation/run?k=100` | Clamped to `k=20` (maximum candidate pool) |
| Missing `data/gold_dataset.json` with indexed documents | Automatically generates gold dataset from ingested chunks and executes evaluation |
| Empty `data/gold_dataset.json` file | Re-generates or returns `400 Bad Request` |
| Reranker failure during evaluation | Gracefully falls back to raw retrieval ranking for that question, logged with warning |

---

## Day 9 — Production Hardening, MIME Validation & Developer Documentation

> [!NOTE]
> Day 9 hardens the backend and frontend for production readiness: magic-byte MIME sniffing prevents extension spoofing, global 500 handling returns safe correlation IDs, ChromaDB and SQLite feature lazy auto-initialization and automatic schema migrations, and the frontend includes non-blocking toast notifications and direct upload CTAs.

### 9.1 Automated Tests

Run the full end-to-end automated test suite across all 11 test modules:

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend
.venv\Scripts\python.exe -m pytest -v
```

**Expected:** All 145 tests pass:
```
====================== 145 passed, 46 warnings in ~45s ======================
```

Verify the frontend production bundle builds cleanly with zero errors:

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\frontend
npm run build
```

**Expected:**
```
✓ 347 modules transformed.
✓ built in ~900ms (0 errors)
```

---

### 9.2 Magic-Byte MIME Validation (`POST /api/v1/documents/upload`)

Security hardening: File extensions can be falsified by attackers (e.g., renaming a dangerous executable `malware.exe` to `invoice.pdf`). 

- The upload endpoint reads the file's first 4,096 bytes and inspects the binary magic numbers using `python-magic-bin` (libmagic wrapper).
- Even if the client sends `Content-Type: application/pdf`, if the magic bytes don't match an allowed document or image MIME type, the server rejects the upload immediately with `415 Unsupported Media Type`.
- If libmagic DLLs are unavailable on a specific platform, it logs a warning and falls back to client-reported MIME type validation gracefully.

**Expected backend log:**
```
DEBUG  MIME detected via magic bytes    detected_mime=application/pdf
```

---

### 9.3 Global Exception Handling & Request ID Tracing

All API traffic is assigned a stable correlation identifier:

1. **`request_id_middleware`**: Injects or echoes `X-Request-ID` into every HTTP request/response and binds `request_id` to `structlog` context.
2. **Global 500 Handler**: Catches any unhandled Python exception, logs the complete traceback internally with the active `request_id`, and returns a clean, safe JSON payload:
   ```json
   {
     "detail": "An internal server error occurred.",
     "request_id": "cda632f7-7bc9-4408-b2ee-18c46a41bed0"
   }
   ```
   No sensitive system paths, secrets, or internal stack traces leak to the client.

---

### 9.4 Fast Health Probe (`HEAD /health`)

Optimized for container orchestrators (Kubernetes liveness/readiness probes) and AWS/GCP load balancers:

- `GET /api/v1/health` → Performs deep connectivity checks against ChromaDB and Redis (returns JSON).
- `HEAD /api/v1/health` → Returns immediate HTTP `200 OK` with zero response body bytes, avoiding unnecessary network payload overhead during high-frequency health polling.

---

### 9.5 Frontend Hardening & UX Polish

1. **Toast Notification System (`DocumentsPage.jsx`)**:
   - Floating non-blocking status notifications for document uploads, deletions, and background job states.
   - Auto-dismisses after 4 seconds with smooth fade-in/fade-out animations.
2. **Empty State Call-to-Action (`QueryPage.jsx`)**:
   - If the user has not uploaded any documents yet, the Query selector displays a friendly empty state card with an **Upload Documents** button that navigates directly to the Documents tab.
3. **Ingestion Error Recovery**:
   - When a background ingestion job fails, the document list displays a red `Failed` badge with an inline tooltip displaying the specific error reason and a **Retry Ingestion** action.

---

### 9.6 SQLite & ChromaDB Resilience

1. **Automatic SQLite Migrations (`sqlite_store.py`)**:
   - Startup migration (`init_sqlite()`) verifies existing database tables and runs `ALTER TABLE documents ADD COLUMN` for `mime_type` and `file_size_bytes` without requiring manual schema migrations or data wipes.
2. **Lazy Initialization (`chromadb_client.py`)**:
   - `get_chroma_client()` and `get_collection()` lazily initialize the ChromaDB client if called in testing contexts or standalone CLI scripts where FastAPI lifespan hooks do not run.

---

### 9.7 Developer Documentation (`README.md`)

A comprehensive, developer-ready `README.md` is provided at the repository root covering:
- System Architecture Diagram (React + FastAPI + ChromaDB + Groq + OpenRouter + Redis)
- Quickstart Guide (Prerequisites, backend setup, frontend setup, environment variables)
- Complete API Reference (`/auth`, `/documents`, `/jobs`, `/query`, `/metrics`, `/evaluation`, `/health`)
- Verification and Test Run instructions

---

### 9.8 PowerShell Verification Commands

```powershell
# 1. Test HEAD health check
$headResp = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health" -Method Head
Write-Host "HEAD Status:" $headResp.StatusCode "Body length:" $headResp.RawContentLength

# 2. Verify X-Request-ID header in response
$resp = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health" -Method Get
Write-Host "Request ID:" $resp.Headers["X-Request-ID"]

# 3. Test magic-byte validation by uploading an invalid spoofed file (renamed text file as PDF)
$fakePdf = [System.IO.Path]::GetTempFileName() + ".pdf"
Set-Content -Path $fakePdf -Value "This is plain text pretending to be a PDF"
try {
  $form = @{ file = Get-Item $fakePdf }
  Invoke-RestMethod -Uri "http://localhost:8000/api/v1/documents/upload" -Method Post -Form $form `
    -Headers @{ Authorization = "Bearer $token" }
} catch {
  Write-Host "Caught expected rejection:" $_.Exception.Response.StatusCode
}
Remove-Item $fakePdf -Force

# 4. Run the full pytest test suite
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend
.venv\Scripts\python.exe -m pytest tests/test_ingestion.py -v
```

**Expected output:**
```
HEAD Status: 200 Body length: 0
Request ID: 3e3cb8ac-e8bd-4840-8141-420391948dbb
Caught expected rejection: UnsupportedMediaType
All 16 ingestion tests PASSED
```

---

### 9.9 Log Reading Guide — Hardened Ingestion & Magic Bytes

```
INFO   File saved                           document_id=3781db... filename=report.pdf size_bytes=104250
DEBUG  MIME detected via magic bytes        detected_mime=application/pdf
INFO   Job created                          job_id=e8f5530e... status=pending request_id=3e3cb8ac...
INFO   HTTP request                         method=POST path=/api/v1/documents/upload status_code=202 latency_ms=48.8 request_id=3e3cb8ac...
INFO   Starting ADE parse                   document_id=3781db... model=dpt-2-latest
INFO   Normalizing ADE chunks               raw_chunk_count=12 page_count=2
INFO   ChromaDB initialized                 collection=ade_documents existing_chunks=45
INFO   Embedding complete                   new_chunks_indexed=12 skipped_chunks=0
INFO   Job completed                        job_id=e8f5530e... status=completed
```

---

### 9.10 Error Cases

| Test | Expected |
|---|---|
| Upload file whose magic bytes do not match allowed MIME types | `415 Unsupported Media Type` (`File type '...' is not supported`) |
| Upload empty file (0 bytes) | `422 Unprocessable Entity` (`Uploaded file is empty.`) |
| Upload file exceeding `MAX_UPLOAD_SIZE_MB` | `413 Request Entity Too Large` |
| `HEAD /api/v1/health` | `200 OK` with 0 body bytes |
| Unhandled exception inside any route | `500 Internal Server Error` with `{"detail": "...", "request_id": "<uuid>"}` |
| SQLite document retrieval with legacy missing columns | Auto-migrated with fallback MIME detection |
| ChromaDB access outside lifespan context | Auto-initialized without throwing `RuntimeError` |

---

## Pipeline Status — What Is Built vs What Remains

| Day | Feature | Status |
|---|---|---|
| 0 | Foundation: FastAPI skeleton, React skeleton, ChromaDB init, Redis init, all schemas | ✅ Built |
| 1 | Upload + Jobs: `POST /documents/upload`, async ingestion, job status, frontend upload form | ✅ Built |
| 2 | ADE + Chunking: real ADE integration, multimodal chunks with bbox/page/type preserved | ✅ Built |
| 3 | Embeddings + Index: OpenRouter NVIDIA embeddings, ChromaDB indexing, idempotency | ✅ Built |
| 4 | Router + Retrieval: query router (text/multimodal/hybrid), Top-N candidates via ChromaDB | ✅ Built |
| 5 | Rerank + LLM: OpenRouter reranker, context assembly, Qwen 3.8 27B + Nemotron fallback, grounded answer | ✅ **Built** |
| 6 | Redis Cache: query-answer caching, cache invalidation on re-ingestion, `/query/history` endpoint, ⚡ cache-hit badge | ✅ **Built** |
| 7 | Observability: 5 benchmark categories, SQLite persistence, `/metrics` endpoint, 📊 Metrics dashboard | ✅ **Built** |
| 8 | Evaluation + Source Grounding: Recall@K / Precision@K, Gold dataset, /evaluation/run endpoint, Evaluation Dashboard, BBox Visual Grounding | ✅ **Built** |
| 9 | Production Hardening: Magic-byte MIME validation, global exception handler + request_id tracing, HEAD /health, toast notifications, empty state CTA, SQLite auto-migrations, full documentation | ✅ **Built** |

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
| `providers/openrouter_reranker.py` | Day 5 | Real `/rerank` API — NVIDIA reranker via OpenRouter, maps scores by index |
| `providers/groq.py` | Day 5 | Groq chat completions — Qwen 3.8 27B, token tracking, cost estimate, retry |
| `providers/openrouter_llm.py` | Day 5 | OpenRouter chat completions — Nemotron 120B fallback, same interface as Groq |
| `services/context_assembly.py` | Day 5 | Dedup chunks, token-budget enforcement, `[Source N]` grounded prompt builder |
| `services/llm_service.py` | Day 5 | Groq primary → OpenRouter fallback orchestration with full provenance |
| `POST /query` (upgraded) | Day 5 | Full pipeline: rerank → assemble context → generate → return grounded answer |
| `schemas/query.py` (`llm_provider` field) | Day 5 | Optional provider selector in `QueryRequest` |
| `QueryPage.jsx` (Day 5 updates) | Day 5 | Provider dropdown, `ModelBadge`, filename in source cards, full latency debug |
| `QueryPage.css` (Day 5 updates) | Day 5 | `.provider-dropdown`, `.model-badge`, `.source-filename` styles |
| `tests/test_query_pipeline.py` | Day 5 | 21 mocked integration tests — full pipeline, fallback, reranker failure |
| `core/config.py` (`CACHE_TTL_SECONDS`) | Day 6 | Configurable cache TTL (default 3600 s = 1 hour) via `.env` |
| `services/cache_service.py` | Day 6 | Full Redis Hash cache — get/set/invalidate/list, key normalisation (SHA-256), graceful degradation |
| `POST /query` (Step 0 + Step 7) | Day 6 | Cache check before pipeline; cache store after generation |
| `GET /query/history` | Day 6 | Lists all cached Q&A pairs for the authenticated user, optional `document_id` filter |
| `services/ingestion_service.py` (Step 0) | Day 6 | `invalidate_document_cache()` fires at the start of every ingestion run |
| `QueryPage.jsx` (cache badge) | Day 6 | ⚡ Instant (cached) amber badge with pulse animation when `cache_hit=true` |
| `QueryPage.css` (`.cache-hit-badge`) | Day 6 | Amber gradient badge, `cache-pulse` keyframe animation |
| `tests/test_cache.py` | Day 6 | 17 mocked unit tests — key format, miss/hit, store, invalidation, list, graceful degradation |
| `schemas/telemetry.py` | Day 7 | `TelemetryRecord` + `MetricsResponse` Pydantic models — all 5 benchmark categories |
| `services/telemetry_service.py` | Day 7 | Async `append_record()` to `data/telemetry.jsonl`; `compute_metrics()` with avg/p95 aggregation |
| `db/sqlite_store.py` | Day 7 | `DocumentSQLiteStore` + `JobSQLiteStore` (async aiosqlite) — replaces in-memory stores |
| `GET /api/v1/metrics` | Day 7 | Aggregated observability metrics — no auth, reads last 5000 telemetry records |
| `app/main.py` (lifespan) | Day 7 | `await init_sqlite()` on startup — creates `documents` + `jobs` tables in `data/rag.db` |
| `POST /query` (Step 8) | Day 7 | `TelemetryRecord` appended after every successful query pipeline run |
| `services/ingestion_service.py` (Step 11) | Day 7 | `TelemetryRecord` appended after every successful ingestion run |
| `pages/MetricsPage.jsx` + `MetricsPage.css` | Day 7 | 📊 Metrics dashboard — glassmorphism cards, color-coded CSS latency bars, 30 s auto-refresh |
| `QueryPage.jsx` (`TelemetryPanel`) | Day 7 | Collapsible ⚙️ Performance Details panel below each answer — latency bars, token counts, cost |
| `Navbar.jsx` + `App.jsx` | Day 7 | 📊 Metrics nav link and `/metrics` route added |
| `tests/test_telemetry.py` | Day 7 | 19 async tests — schema validation, append/load, aggregation (avg/p95/credits/cost), endpoint |
| `app/evaluation/gold_dataset.py` | Day 8 | Gold dataset schema, loader from `data/gold_dataset.json`, rule-based auto-generation from chunks |
| `app/evaluation/evaluator.py` | Day 8 | Metric calculation (`recall_at_k`, `precision_at_k`), full pipeline evaluator (pre & post rerank) |
| `app/api/v1/endpoints/evaluation.py` | Day 8 | `GET /evaluation/run` endpoint, k validation, ChromaDB check, aggregate & per-question reporting |
| `data/gold_dataset.json` | Day 8 | Curated gold question dataset with expected document & chunk IDs for grounded evaluation |
| `pages/EvaluationPage.jsx` + `EvaluationPage.css` | Day 8 | 🎯 Evaluation dashboard — K-selector, metric cards with improvement badges, per-question comparison table |
| `QueryPage.jsx` (`BBoxGrounding`) | Day 8 | Visual page thumbnail SVG with coordinate-mapped bounding box highlight per chunk type |
| `Navbar.jsx` + `App.jsx` | Day 8 | 🎯 Evaluation nav link and `/evaluation` route added |
| `tests/test_evaluation.py` | Day 8 | 26 unit tests — Recall@K, Precision@K, gold dataset helpers, file IO, pipeline evaluation |
| `api/v1/endpoints/documents.py` (MIME sniffing) | Day 9 | Magic-byte MIME detection via `python-magic-bin` with graceful fallback |
| `api/v1/endpoints/documents.py` (Replace/Overwrite) | Day 9 | Automatically replaces existing document with same filename, purging old ChromaDB chunks, Redis cache, and SQLite records |
| `api/v1/endpoints/documents.py` (`DELETE /documents/{id}`) | Day 9 | Document deletion endpoint with full cascading cleanup across vector store, cache, and DB |
| `db/sqlite_store.py` (schema migration & cascade) | Day 9 | Column migrations for `mime_type` and `file_size_bytes` + `get_by_filename`, `delete`, `delete_by_document` |
| `db/chromadb_client.py` (lazy init) | Day 9 | Auto-initialize collection and client on demand when accessed outside lifespan |
| `pages/DocumentsPage.jsx` (Toast system & Delete) | Day 9 | Toast notifications, inline error recovery, and document delete button with confirmation |
| `pages/QueryPage.jsx` (Empty state CTA) | Day 9 | "No documents uploaded yet" prompt with direct navigate-to-upload button |
| `README.md` | Day 9 | Comprehensive root documentation covering architecture, setup, endpoints, benchmarks |



