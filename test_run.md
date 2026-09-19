# Test Run Guide — Multimodal RAG Platform (Day 0 + 1 + 2)

> **Status built:** Foundation · Upload + Ingestion · ADE + Chunking  
> **Stack:** FastAPI (Python 3.12) · React + Vite · LandingAI ADE · ChromaDB · Redis (Upstash)

---

## 1. Prerequisites

Make sure these are running / installed before you start:

| Requirement | Check |
|---|---|
| Python 3.12 in `.venv` | `backend\.venv\Scripts\python.exe --version` |
| Node.js ≥ 18 | `node --version` |
| `backend\.env` populated | All API keys present |
| Internet access | ADE API + Upstash Redis need connectivity |

---

## 2. Start the Backend

Open a terminal and run from the **`backend/`** folder:

```powershell
# Navigate to backend
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend

# Start the FastAPI dev server inside .venv
.venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected startup output:**
```
INFO  Starting Multimodal RAG API version=0.1.0
INFO  ChromaDB initialized  collection=ade_documents
INFO  Redis ping successful
INFO  All services initialized. Ready to serve.
INFO  Uvicorn running on http://0.0.0.0:8000
```

> [!NOTE]
> If Redis shows a warning instead of success, that's fine for Day 1/2 — caching is a Day 6 feature.  
> ChromaDB **must** initialize cleanly (check `data/chroma_db/` is created).

---

## 3. Start the Frontend

Open a **second terminal** and run from **`frontend/`**:

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\frontend

npm run dev
```

**Expected output:**
```
  VITE v5.x  ready in 300ms
  ➜  Local:   http://localhost:5173/
```

Open **http://localhost:5173** in your browser.

---

## 4. Automated Tests

Run from **`backend/`** — no server needs to be running:

```powershell
cd C:\Users\susmi\OneDrive\Desktop\Agentic_RAG\backend

# Full test suite (Day 0 + 1 + 2)
.venv\Scripts\python.exe -m pytest tests/test_health.py tests/test_ingestion.py tests/test_chunking.py -v

# Just chunking tests (Day 2, mocked — 0 ADE credits)
.venv\Scripts\python.exe -m pytest tests/test_chunking.py -v

# All tests
.venv\Scripts\python.exe -m pytest -v
```

**Expected:** `34 passed` across health + ingestion + chunking.

> [!IMPORTANT]
> Tests write to a **temporary directory** (auto-deleted after the run).  
> `data/uploads/` and `data/ade_outputs/` stay clean — never polluted by tests.

---

## 5. Manual Test Checklist

### 5.1 — Health Check

```powershell
curl http://localhost:8000/api/v1/health
```

**Expected response:**
```json
{
  "status": "ok",
  "chromadb": true,
  "redis": true
}
```

Also verify: **http://localhost:8000/docs** — Swagger UI loads with all routes listed.

---

### 5.2 — Register + Login (Frontend)

1. Open **http://localhost:5173**
2. You should be redirected to **`/login`**
3. Click **"Register"** → fill in username, email, password → submit
4. You should be redirected back to `/login` after registration
5. Log in with the credentials you just created
6. You should land on the **Documents** page (`/`)

> [!NOTE]
> JWT token is stored in `localStorage`. Refresh the page — you should stay logged in.

**Also test via API:**
```powershell
# Register
curl -X POST http://localhost:8000/api/v1/auth/register `
  -H "Content-Type: application/json" `
  -d '{"username":"testuser","email":"test@example.com","password":"Test1234!"}'

# Login -> copy the access_token from the response
curl -X POST http://localhost:8000/api/v1/auth/login `
  -F "username=testuser" `
  -F "password=Test1234!"
```

---

### 5.3 — Upload a Document (Frontend)

1. On the Documents page, drag & drop **`backend/sample_docs/mixed_sample.pdf`** onto the upload zone  
   (or click **"Choose File"** and pick it)
2. Watch the upload progress bar fill to 100%
3. The document card appears immediately with status **Pending**
4. Within seconds it changes to **Processing** (polling every 2s)
5. After ADE finishes (~5–15 s for a 1-page doc): **Complete**
6. The meta row shows: `PDF · XX KB · 🧩 N chunks · dpt-2-20260410 · 💳 X.X credits`

> [!IMPORTANT]
> This is the **first real ADE API call** — it will consume ADE credits.  
> The sample doc (`mixed_sample.pdf`) has 1 page → costs ~3 credits.

---

### 5.4 — View Details Panel (Frontend)

After a document completes:

1. Click **▼ View Details** below the meta row
2. The panel expands showing a grid with:
   - **Filename** — original file name
   - **File Type** — PDF / DOCX / etc.
   - **File Size** — in KB
   - **Total Chunks** — 🧩 N (purple highlight)
   - **Parser Version** — `dpt-2-20260410` (monospace chip)
   - **ADE Credits Used** — 💳 X.XX (green)
   - **Document ID** — first 16 chars of SHA-256 hash + ellipsis
   - **Status** — Complete badge
3. Click **▲ Hide Details** to collapse

---

### 5.5 — Verify ADE Output Files

After a successful upload, check the files created on disk:

```powershell
Get-ChildItem backend\data\ade_outputs -Recurse | Select-Object FullName
```

**Expected for each document:**
```
data/ade_outputs/{document_id}/raw.json       <- Full ADE API response
data/ade_outputs/{document_id}/document.md    <- Full document markdown
data/ade_outputs/{document_id}/chunks.json    <- Normalized Chunk objects
```

**Spot-check `chunks.json`:**
```powershell
$docId = (Get-ChildItem backend\data\ade_outputs -Directory)[0].Name
Get-Content "backend\data\ade_outputs\$docId\chunks.json" |
  ConvertFrom-Json |
  Select-Object -First 1 |
  ConvertTo-Json -Depth 5
```

**Expected chunk shape:**
```json
{
  "chunk_id": "abc123...",
  "document_id": "sha256...",
  "chunk_type": "text",
  "text": "<a id='...'></a>\n\nActual text content here",
  "page": 0,
  "bbox": [0.145, 0.069, 0.853, 0.105],
  "source": "mixed_sample.pdf",
  "parser_version": "dpt-2-20260410",
  "ade_chunk_id": "b5b47447-...",
  "confidence": 0.995,
  "image_data": null
}
```

**Verify table chunk is NOT flattened (HTML preserved):**
```powershell
Get-Content "backend\data\ade_outputs\$docId\chunks.json" |
  ConvertFrom-Json |
  Where-Object { $_.chunk_type -eq "table" } |
  Select-Object -ExpandProperty text
```
Should contain `<table>`, `<tr>`, `<td>` — not plain text.

---

### 5.6 — Idempotency Test

**Upload the SAME file a second time:**

1. Drag & drop `mixed_sample.pdf` again
2. Response should be **instant** (no ADE call) with:  
   `"Document already exists. Returning existing record."`
3. Same `document_id` is returned
4. Backend logs show:
   ```
   ADE cache hit — skipping API call
   ```
5. No new files created in `data/ade_outputs/`
6. ADE credit usage stays at 0 for the second call

---

### 5.7 — Upload Different File Types

| File | Expected chunk types |
|---|---|
| PDF with text + tables | text, table |
| PDF with charts/figures | text, figure |
| `.png` / `.jpg` image | figure |
| `.docx` Word document | text, table |

Verify status reaches Complete for each.

---

### 5.8 — API Endpoints (Swagger)

Go to **http://localhost:8000/docs** and test manually:

#### `GET /api/v1/health` (no auth needed)

#### `GET /api/v1/documents/` (JWT required)
- Click **Authorize** in Swagger, paste your `access_token`
- Returns list of your documents with all metadata fields

#### `GET /api/v1/documents/{document_id}`
- Returns full `DocumentMetadata` including `chunk_count`, `parser_version`, `ade_credits_used`
- Try an unknown ID → `404 Not Found`

#### `GET /api/v1/jobs/{job_id}`
- Returns job with `status`, `chunks_created`, `progress_message`
- Try another user's job → `403 Forbidden`

---

### 5.9 — Error Cases

| Test | Expected HTTP |
|---|---|
| Upload a `.txt` file | `415 Unsupported Media Type` |
| Upload an empty file | `422 Unprocessable Entity` |
| Upload without JWT | `401 Unauthorized` |
| `GET /documents/unknown-id` | `404 Not Found` |
| `GET /jobs/unknown-id` | `404 Not Found` |

---

### 5.10 — Switch ADE Model (No Code Change)

To try `dpt-3-pro` (higher accuracy for scanned docs):

1. Edit `backend/.env`:
   ```
   ADE_MODEL=dpt-3-pro
   ```
2. Restart the backend (`Ctrl+C` then re-run uvicorn)
3. Upload a **new** document (different content = different SHA-256 = fresh ADE call)
4. Check `data/ade_outputs/{id}/raw.json` → `metadata.version` field should reflect the new model

---

## 6. Log Reading Guide

Backend logs are structured JSON. Key events to watch in the server terminal:

```
# Normal upload + ADE flow:
Ingestion started        status=processing
Calling ADE provider     model=dpt-2-latest  file=mixed_sample.pdf
ADE parse successful     chunk_count=4  credit_usage=3.0  page_count=1
Persisted raw.json
Persisted document.md
Normalizing ADE chunks   raw_chunk_count=4
Chunk normalization complete   total_normalized=4  skipped_empty=0
Persisted chunks.json    chunk_count=4
Ingestion completed      credits_used=3.0  parser_version=dpt-2-20260410

# Second upload of same file (idempotency):
ADE cache hit — skipping API call
Ingestion completed      credits_used=0.0
```

---

## 7. What Is NOT Yet Built

| Day | Feature | Status |
|---|---|---|
| 3 | ChromaDB vector embedding + indexing | Not built |
| 4 | Query router + retrieval (text / multimodal / hybrid) | Not built |
| 5 | Reranker + LLM answer generation (Groq / OpenRouter) | Not built |
| 6 | Redis query-answer cache | Not built |
| 7 | Observability + SQLite persistence | Not built |
| 8 | RAG evaluation + Docker Compose | Not built |

The **`/query`** page exists but returns a stub. The **Query →** button on each document card navigates there — it won't produce answers yet.
