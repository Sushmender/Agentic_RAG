# Implementation Tasks — Multimodal RAG Platform

> Track: Day 0 (Foundation) + Day 1–8 (Full Pipeline Implementation)
> Stack: FastAPI · React · LandingAI ADE · ChromaDB · OpenRouter (NVIDIA models) · Groq · Redis

---

## Day 0 — Foundation & Project Setup

### Backend
- [x] Create root directory structure: `backend/`, `frontend/`, `data/uploads/`, `data/ade_outputs/`, `data/chroma_db/`
- [x] Initialize Python virtual environment (`.venv`) in `backend/`
- [x] Create `backend/requirements.txt` with: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `python-multipart`, `httpx`, `chromadb`, `redis`, `tenacity`, `structlog`, `python-dotenv`, `aiofiles`, `pytest`, `pytest-asyncio`, `httpx`
- [x] Install all dependencies into `.venv`
- [x] Create `backend/.env.example` with all required env vars: `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `LANDINGAI_API_KEY`, `REDIS_URL`, `CHROMA_DB_PATH`, `ADE_OUTPUT_DIR`, `UPLOAD_DIR`, `LOG_LEVEL`, `MAX_UPLOAD_SIZE_MB`, `EMBEDDING_MODEL`, `RERANKER_MODEL`, `PRIMARY_LLM_MODEL`, `FALLBACK_LLM_MODEL`, `CACHE_TTL_SECONDS`, `RETRIEVAL_TOP_N`, `RERANK_TOP_K`
- [x] Create `backend/.env` (from `.env.example`, with real local values — gitignored)
- [x] Create `backend/.gitignore` — exclude `.env`, `.venv/`, `__pycache__/`, `data/`
- [x] Create `backend/app/__init__.py`
- [x] Create `backend/app/core/config.py` — Pydantic `Settings` class loading all env vars with validation
- [x] Create `backend/app/core/logging.py` — `structlog` structured JSON logger with request_id support
- [x] Create `backend/app/core/errors.py` — custom `HTTPException` subclasses: `DocumentNotFoundError`, `JobNotFoundError`, `ChunkNotFoundError`, `ProviderError`, `ValidationError`
- [x] Create `backend/app/core/retries.py` — `tenacity` retry decorators with configurable attempts, wait, timeout
- [x] Create `backend/app/schemas/document.py` — `Document`, `DocumentMetadata`, `DocumentStatus` (pending/processing/completed/failed) Pydantic models
- [x] Create `backend/app/schemas/chunk.py` — `ChunkType` enum (text/table/figure), `Chunk` model with: `chunk_id`, `document_id`, `chunk_type`, `text`, `page`, `bbox` `[x0,y0,x1,y1]`, `source`, `parser_version`
- [x] Create `backend/app/schemas/job.py` — `Job`, `JobStatus` Pydantic models with `job_id`, `document_id`, `status`, `created_at`, `updated_at`, `error`
- [x] Create `backend/app/schemas/query.py` — `QueryRequest`, `QueryResponse`, `RetrievalResult`, `RerankResult`, `Source` (with `document_id`, `chunk_id`, `page`, `bbox`, `chunk_type`) Pydantic models
- [x] Create `backend/app/providers/base.py` — abstract base classes: `BaseEmbeddingProvider`, `BaseRerankerProvider`, `BaseLLMProvider`, `BaseADEProvider`
- [x] Create `backend/app/providers/openrouter.py` — `OpenRouterClient` stub (shared HTTP client, auth header injection)
- [x] Create `backend/app/providers/groq.py` — `GroqClient` stub
- [x] Create `backend/app/providers/ade.py` — `ADEProvider` stub (inherits `BaseADEProvider`)
- [x] Create `backend/app/db/chromadb_client.py` — initialize `chromadb.PersistentClient`, create/get `ade_documents` collection on startup
- [x] Create `backend/app/db/redis_client.py` — initialize `redis.asyncio.Redis` client, ping on startup
- [x] Create `backend/app/api/v1/endpoints/health.py` — `GET /health` returns `{"status": "ok", "chromadb": bool, "redis": bool}`
- [x] Create `backend/app/api/v1/endpoints/documents.py` — stub routes: `POST /documents/upload`, `GET /documents/{document_id}`, `GET /documents/{document_id}/chunks/{chunk_id}`
- [x] Create `backend/app/api/v1/endpoints/jobs.py` — stub route: `GET /jobs/{job_id}`
- [x] Create `backend/app/api/v1/endpoints/query.py` — stub route: `POST /query`
- [x] Create `backend/app/api/v1/router.py` — include all endpoint routers under `/api/v1`
- [x] Create `backend/app/main.py` — FastAPI app factory with lifespan (ChromaDB init, Redis ping), CORS, router inclusion, global exception handler
- [x] Create `backend/Makefile` — targets: `make dev`, `make test`, `make lint`
- [x] Create `backend/tests/test_health.py` — verify `/health` returns 200 with correct shape

### Frontend
- [x] Initialize React + Vite project in `frontend/` using `npm create vite@latest . -- --template react`
- [x] Install frontend dependencies: `axios`, `react-router-dom`, `react-dropzone`
- [x] Create `frontend/.env.example` with `VITE_API_BASE_URL=http://localhost:8000/api/v1`
- [x] Create `frontend/.gitignore` — exclude `node_modules/`, `dist/`, `.env`
- [x] Create `frontend/src/services/api.js` — axios instance with base URL from env, request/response interceptors
- [x] Create `frontend/src/App.jsx` — root with React Router (`/` → DocumentsPage, `/query` → QueryPage)
- [x] Create `frontend/src/pages/DocumentsPage.jsx` — stub page
- [x] Create `frontend/src/pages/QueryPage.jsx` — stub page
- [x] Create `frontend/src/components/layout/Navbar.jsx` — navigation bar

### Verification
- [x] `uvicorn app.main:app --reload` starts without errors in `backend/.venv`
- [x] `GET /health` returns `200 {"status": "ok"}` (or degraded if Redis is missing, which is handled gracefully)
- [x] ChromaDB `ade_documents` collection created at `data/chroma_db/`
- [x] Redis client pings successfully (local Redis running, or warns gracefully in dev)
- [x] `npm run dev` starts frontend without errors
- [x] Frontend `/` page loads in browser (Verified React Server)
- [x] Frontend `api.js` can reach backend `/health` (no CORS errors)
- [x] `pytest backend/tests/test_health.py` passes (via tests added)
- [x] Config loads all env vars from `.env` with Pydantic validation

---

## Day 1 — Document Upload + Async Ingestion + Job Tracking

### Backend
- [ ] Implement `POST /documents/upload` — accept multipart file, validate MIME type (PDF/DOCX/PPTX/XLSX/PNG/JPG), enforce `MAX_UPLOAD_SIZE_MB`
- [ ] Generate stable `document_id` = `SHA-256(file_content)` — same file → same ID (idempotency)
- [ ] Save uploaded file to `data/uploads/{document_id}/{original_filename}`
- [ ] Create `Document` metadata record on upload: `document_id`, `filename`, `document_type`, `version`, `created_at`, `status=pending`, `source`, `parser_version=None`
- [ ] Create `Job` record tied to `document_id` with `status=pending`
- [ ] Launch async ingestion via `FastAPI.BackgroundTasks` — `POST /documents/upload` returns immediately with `document_id` + `job_id`
- [ ] Create `backend/app/services/ingestion_service.py` — async ingestion coordinator: update job to `processing`, call ADE stub, update job to `completed` or `failed`
- [ ] Create in-memory `DocumentStore` and `JobStore` (dict-based, keyed by ID) — to be replaced in Day 7
- [ ] Implement `GET /documents/{document_id}` — return `Document` metadata or `404`
- [ ] Implement `GET /jobs/{job_id}` — return `Job` with status or `404`
- [ ] Implement `GET /documents/` — list all documents with status
- [ ] Log job status transitions with `structlog` including `document_id`, `job_id`, `status`, timestamp
- [ ] Create `backend/tests/test_ingestion.py` — test upload, idempotency (same file → same document_id), job creation, status polling

### Frontend
- [ ] Implement drag-and-drop upload form in `DocumentsPage.jsx` using `react-dropzone`
- [ ] Show upload progress indicator
- [ ] After upload, poll `GET /jobs/{job_id}` every 2 seconds until `completed` or `failed`
- [ ] Display document list with `status` badge (color-coded: pending=gray, processing=yellow, completed=green, failed=red)
- [ ] Display error messages from failed jobs
- [ ] Navigate to `/query` when a document completes

### Verification
- [ ] Upload a PDF → response contains `document_id` and `job_id`
- [ ] Same PDF uploaded twice → same `document_id`, no duplicate job (idempotent)
- [ ] `GET /jobs/{job_id}` transitions from `pending` → `processing` → `completed`
- [ ] `GET /documents/{document_id}` returns correct metadata
- [ ] `GET /documents/` lists uploaded documents
- [ ] Frontend upload form uploads file and shows real-time status
- [ ] `pytest backend/tests/test_ingestion.py` passes

---

## Day 2 — ADE Integration + Multimodal Chunk Normalization

### Backend
- [ ] Implement `backend/app/providers/ade.py` — real LandingAI ADE Parse API integration:
  - HTTP call to ADE Parse API with document binary
  - Use **DPT-3 Verity** tier for clean/digital documents by default
  - Use **DPT-3 Pro** tier as fallback for scanned/complex documents
  - Track ADE credit consumption per call
  - Retry on ADE API failures using `tenacity`
- [ ] Idempotent ADE: check if `data/ade_outputs/{document_id}/chunks.json` exists — skip API call if so
- [ ] Persist ADE output: save raw JSON to `data/ade_outputs/{document_id}/raw.json`, save processed markdown to `data/ade_outputs/{document_id}/document.md`
- [ ] Create `backend/app/services/chunking_service.py` — normalize ADE output into production `Chunk` schema:
  - Map ADE `chunk_type` → `ChunkType` enum (text/table/figure)
  - Preserve `bbox [x0, y0, x1, y1]` (normalized 0–1)
  - Preserve `page` (0-indexed)
  - Add `document_id`, `source` (filename), `parser_version` (ADE version)
  - Generate stable `chunk_id` = `SHA-256(document_id + page + str(bbox) + chunk_type)`
  - Filter out empty/whitespace-only chunks
  - DO NOT flatten tables/figures to plain text — preserve original content
- [ ] Save normalized chunks to `data/ade_outputs/{document_id}/chunks.json`
- [ ] Update `Document` metadata: `parser_version`, `status=completed`, chunk count
- [ ] Log ADE credit usage per document in structured log
- [ ] Create `backend/tests/test_chunking.py` — test chunk normalization, idempotency, empty chunk filtering

### Frontend
- [ ] Display chunk count on document card after ingestion completes
- [ ] Add "View Details" to document card showing: filename, type, pages, chunk count, parser version
- [ ] Add ADE credit indicator (show credits used if available from API response)

### Verification
- [ ] Upload PDF → ADE called → `data/ade_outputs/{document_id}/chunks.json` created
- [ ] Same document uploaded again → ADE NOT called again (idempotency verified via logs)
- [ ] Chunks have correct schema: `chunk_id`, `document_id`, `chunk_type`, `text`, `page`, `bbox`, `source`, `parser_version`
- [ ] Table chunks NOT flattened — HTML/markdown table content preserved in `text`
- [ ] Figure chunks have description or placeholder text preserved
- [ ] `pytest backend/tests/test_chunking.py` passes
- [ ] Frontend shows chunk count on document card

---

## Day 3 — Multimodal Embeddings + ChromaDB Indexing

### Backend
- [ ] Implement `backend/app/providers/openrouter_embedding.py` — real OpenRouter embedding client:
  - Model: `nvidia/llama-nemotron-embed-vl-1b-v2`
  - Support **passage mode** (for indexing chunks)
  - Support **query mode** (for embedding user queries)
  - Batch requests: configurable `EMBEDDING_BATCH_SIZE` (default 16)
  - Retry on HTTP 429/5xx with exponential backoff
  - Track: model name, token count, calculated cost, latency
- [ ] Implement full `backend/app/db/chromadb_client.py`:
  - Persistent client at `data/chroma_db/`
  - Collection: `ade_documents`
  - Schema: `document_id`, `chunk_id`, `chunk_type`, `page`, `bbox_x0`, `bbox_y0`, `bbox_x1`, `bbox_y1` in metadata
  - `upsert_chunks(chunks, embeddings)` — idempotent: existing chunk_ids skipped
  - `query_similar(embedding, n_results, filter_metadata)` — cosine similarity search
  - `get_chunk(chunk_id)` — fetch single chunk by ID
  - `delete_document(document_id)` — remove all chunks for a document
  - `get_collection_stats()` — count, document breakdown
- [ ] Create `backend/app/services/embedding_service.py`:
  - Load chunks from `data/ade_outputs/{document_id}/chunks.json`
  - Check ChromaDB for existing chunk IDs → skip already-indexed
  - Batch remaining chunks → call OpenRouter embeddings
  - Upsert into ChromaDB with metadata
  - Log: new chunks indexed, skipped, total, embedding cost
- [ ] Wire embedding service into ingestion pipeline (called after chunking)
- [ ] Implement `GET /documents/{document_id}/chunks/{chunk_id}` — return chunk metadata from ChromaDB
- [ ] Create `backend/tests/test_embedding.py` — test batch embedding, ChromaDB upsert, idempotency

### Frontend
- [ ] Update document detail view to show: total chunks in ChromaDB, embedding model used
- [ ] Add ChromaDB collection stats to a simple admin/debug panel (optional)

### Verification
- [ ] Upload PDF → chunks embedded → ChromaDB `ade_documents` count matches chunk count
- [ ] Re-run ingestion → NO new embeddings generated (idempotency: log shows "0 new chunks")
- [ ] `GET /documents/{document_id}/chunks/{chunk_id}` returns correct chunk with bbox/page
- [ ] Embedding batch size respected (no single API call > `EMBEDDING_BATCH_SIZE` chunks)
- [ ] Embedding cost logged in structured output
- [ ] `pytest backend/tests/test_embedding.py` passes

---

## Day 4 — Query Router + Text/Multimodal/Hybrid Retrieval

### Backend
- [ ] Create `backend/app/services/query_router.py` — rule-based router:
  - Define multimodal trigger keywords: `table`, `chart`, `figure`, `image`, `graph`, `plot`, `diagram`, `visual`, `picture`, `scan`, `handwritten`, `layout`, `column`, `row`
  - **Text route**: no multimodal keywords, no visual question markers
  - **Multimodal route**: query contains multimodal trigger keywords
  - **Hybrid route**: query asks about both text content and visual elements
  - Return `RouteType` enum: `text | multimodal | hybrid`
  - NO large LLM call for routing — deterministic keyword/heuristic only
- [ ] Create `backend/app/services/retrieval_service.py`:
  - `retrieve_text(query_embedding, document_ids, top_n)` → ChromaDB query, filter `chunk_type=text`, return Top-N
  - `retrieve_multimodal(query_embedding, document_ids, top_n)` → ChromaDB query, all chunk types, return Top-N
  - `retrieve_hybrid(query_embedding, document_ids, top_n)` → merge text + multimodal candidate sets, deduplicate by `chunk_id`, return Top-N
  - Each result includes: `chunk_id`, `document_id`, `chunk_type`, `page`, `bbox`, `text`, `similarity_score`
  - Support optional `document_ids` filter (query specific documents)
  - Default `top_n=20` — enough for reranker to work effectively
- [ ] Embed user query using OpenRouter (query mode)
- [ ] Wire router + retrieval into `POST /query` stub (returns candidate list, not yet reranked)
- [ ] Create `backend/tests/test_retrieval.py` — test each route type, filter behavior, Top-N count

### Frontend
- [ ] Implement query form in `QueryPage.jsx`:
  - Text input for question
  - Optional: document selector (filter by document_id)
  - Submit button
- [ ] Display raw retrieval results (pre-reranking) as a debug option (hidden behind toggle)
- [ ] Show detected route type (text/multimodal/hybrid) as a tag

### Verification
- [ ] Query "What is the revenue?" → route=text, returns text chunks
- [ ] Query "Show me the revenue table" → route=multimodal, returns table/figure chunks
- [ ] Query "Describe the chart and its text caption" → route=hybrid, returns mixed chunks
- [ ] `top_n=20` candidate chunks returned for all route types
- [ ] Results include `chunk_type`, `page`, `bbox`, `similarity_score`
- [ ] `pytest backend/tests/test_retrieval.py` passes

---

## Day 5 — Reranking + Context Assembly + LLM Generation

### Backend
- [ ] Implement `backend/app/providers/openrouter_reranker.py`:
  - Model: `nvidia/llama-nemotron-rerank-vl-1b-v2`
  - Input: query + list of candidate chunks (Top-N from retrieval)
  - Output: reranked list with relevance scores
  - Never rerank full collection — only retrieved Top-N candidates
  - Retry on failure; track latency and usage
- [ ] Create `backend/app/services/context_assembly.py`:
  - Select Top-K (default 5) from reranked candidates
  - Deduplicate exact/near-duplicate chunks (same `chunk_id`)
  - Preserve provenance: `document_id`, `chunk_id`, `page`, `bbox`, `chunk_type`
  - Enforce LLM context window: truncate if total tokens exceed `MAX_CONTEXT_TOKENS`
  - Flag visual chunks (`chunk_type != text`) for special handling in LLM prompt
- [ ] Implement `backend/app/providers/groq.py`:
  - Real Groq API client for Qwen 27B
  - Async HTTP call with `httpx`
  - Retry on failure; track latency, input/output tokens, cost
- [ ] Implement `backend/app/providers/openrouter_llm.py`:
  - Real OpenRouter client for `nvidia/nemotron-3-super-120b-a12b:free`
  - Same interface as Groq provider
- [ ] Create `backend/app/services/llm_service.py`:
  - Build grounded prompt: "Answer using ONLY the provided evidence. Cite sources."
  - Try Groq (Qwen 27B) first
  - On Groq failure/timeout → auto-fallback to OpenRouter (Nemotron 120B)
  - Log which provider was used, why fallback triggered
  - Return structured `{ answer, sources, model_used, provider_used }`
- [ ] Complete `POST /query` endpoint — full pipeline:
  - Route → Embed query → Retrieve Top-N → Rerank → Assemble context → Generate → Return grounded response
  - Support `llm_provider` selection from `QueryRequest` (default Groq, fallback OpenRouter if requested)
  - Response: `{ answer, sources: [{ document_id, chunk_id, page, bbox, chunk_type }], latency_ms, model_used }`
- [ ] Create `backend/tests/test_query_pipeline.py` — integration test for full pipeline

### Frontend
- [ ] Display final answer in styled answer box
- [ ] Display source cards below answer: document name, page number, chunk type badge
- [ ] Show `bbox` as text coordinates (visual highlight reserved for Day 8)
- [ ] Show model used (Groq/Qwen or OpenRouter/Nemotron) and latency
- [ ] Add dropdown in `QueryPage.jsx` to allow user to select between Qwen 32B (Groq) and Nemotron 120B (OpenRouter)

### Verification
- [ ] `POST /query` returns `{ answer, sources }` with correct schema
- [ ] Sources contain `document_id`, `chunk_id`, `page`, `bbox`, `chunk_type`
- [ ] Fallback triggers when Groq key invalid → response still returns from OpenRouter
- [ ] Answer references document evidence (not hallucinated)
- [ ] Reranker called with Top-N (≤20) candidates, returns Top-K (≤5)
- [ ] `pytest backend/tests/test_query_pipeline.py` passes

---

## Day 6 — Redis Query-Answer Cache

### Backend
- [ ] Implement full `backend/app/db/redis_client.py`:
  - `redis.asyncio.Redis` client using `REDIS_URL` from config
  - `async_ping()` — liveness check
  - `get(key)` / `set(key, value, ttl)` / `delete(key)` / `delete_pattern(pattern)` wrappers
- [ ] Implement full `backend/app/db/redis_client.py`:
  - Upstash Redis connection via `REDIS_URL` from config (TLS `rediss://` URL)
  - `redis.asyncio.Redis.from_url(REDIS_URL)` client
  - Hash structure: `user:{user_id}:qa:{doc_id}` — fields: `question`, `answer`
  - `async_ping()` — liveness check
  - `hset(key, field, value)` / `hget(key, field)` / `hgetall(key)` wrappers
  - `scan_delete_pattern(pattern)` using `SCAN` (never `KEYS`) for cache invalidation
- [ ] Create `backend/app/services/cache_service.py`:
  - Cache key: `user:{user_id}:qa:{document_id}` (Redis Hash per user+document)
  - Field key: `SHA-256(normalize(query))` where normalize = lowercase + strip whitespace
  - `get_cached_response(user_id, document_id, query)` → `HGET` → returns `QueryResponse` if hit, else `None`
  - `set_cached_response(user_id, document_id, query, response)` → `HSET` on hash key
  - `invalidate_document_cache(document_id)` → `SCAN` for all `*:qa:{document_id}` keys → `DEL` each
  - `list_user_qa_pairs(user_id, document_id)` → `HGETALL user:{user_id}:qa:{document_id}` → return all Q&A pairs
- [ ] Integrate cache into `POST /query` endpoint:
  - Require authenticated `user_id` from JWT header before any cache operation
  - Before pipeline: check cache → if hit, return immediately with `cache_hit=True`
  - After pipeline: store result in cache
  - Add `cache_hit: bool` field to `QueryResponse`
- [ ] Trigger `invalidate_document_cache(document_id)` when document is re-ingested
- [ ] Add cache hit/miss to structured logs with user_id + document_id (not full query text)
- [ ] Create `backend/tests/test_cache.py` — test cache hit, miss, invalidation, key normalization, `list_user_qa_pairs`

### Frontend
- [ ] Show cache hit badge in answer header: `⚡ Instant answer (cached)`
- [ ] Optionally show cache TTL remaining (if returned by API)
- [ ] Differentiate cached vs. fresh answers visually

### Verification
- [ ] Ask same question twice → second response is instant, `cache_hit=true` in response
- [ ] Different questions → both cache misses, both stored in Redis
- [ ] Re-upload same document → cache invalidated → next query is a cache miss
- [ ] Cache key includes user_id (or anonymous session) → different users get separate caches
- [ ] `CACHE_TTL_SECONDS` respected (key expires after TTL)
- [ ] `pytest backend/tests/test_cache.py` passes

---

## Day 7 — Observability, Telemetry, Persistent Storage

### Backend
- [ ] Update `backend/app/core/logging.py` — inject `request_id` (UUID) into every request via middleware
- [ ] Add per-stage timing to pipeline: ADE, embedding, retrieval, reranking, LLM, total end-to-end
- [ ] Create `backend/app/schemas/telemetry.py` — `TelemetryRecord` model capturing all 5 benchmark categories:
  1. `latency_ms`: `{ total, ade, embedding, retrieval, reranking, llm }`
  2. `token_usage`: `{ input_tokens, output_tokens, total_tokens }`
  3. `ade_credits`: `{ per_ingestion, cumulative }`
  4. `embedding_cost`: `{ model, provider, token_count, cost_usd }`
  5. `llm_cost`: `{ model, provider, input_tokens, output_tokens, cost_usd }`
- [ ] Persist `TelemetryRecord` to `data/telemetry.jsonl` (append-only JSON Lines)
- [ ] Replace in-memory `DocumentStore` / `JobStore` with SQLite-backed persistent store using `aiosqlite`:
  - Tables: `documents`, `jobs`
  - Job status updates survive server restart
- [ ] Create `backend/app/api/v1/endpoints/metrics.py` — `GET /metrics`:
  - Aggregate from `data/telemetry.jsonl`
  - Return: avg/p95 latency per stage, total token usage, total cost, ADE credits consumed
- [ ] Add `RETRY_MAX_ATTEMPTS`, `TIMEOUT_SECONDS` to config — use in all provider clients
- [ ] Create `backend/tests/test_telemetry.py` — verify all 5 benchmark fields populated per query

### Frontend
- [ ] Add telemetry panel to query results:
  - Latency breakdown bar chart (ADE / Embedding / Retrieval / Reranking / LLM)
  - Token count (input/output)
  - Estimated cost per query
- [ ] Add metrics dashboard page `MetricsPage.jsx` with:
  - Average end-to-end latency
  - Total queries served
  - Cache hit rate
  - Total embedding cost
  - Total LLM cost

### Verification
- [ ] `GET /metrics` returns all 5 benchmark categories with real data
- [ ] Per-query telemetry logged to `data/telemetry.jsonl`
- [ ] Job state persists across server restart (SQLite)
- [ ] All provider calls use retry/timeout from config
- [ ] Frontend shows latency breakdown per query
- [ ] `pytest backend/tests/test_telemetry.py` passes

---

## Day 8 — RAG Evaluation + Production Hardening

### Backend
- [ ] Create `backend/evaluation/gold_dataset.py`:
  - Gold dataset format: `[{ "question", "expected_document_ids": [], "expected_chunk_ids": [] }]`
  - Load from `data/gold_dataset.json` if exists
  - If no gold dataset: generate minimal one from first 5 ingested documents using rule-based extraction (no LLM)
  - Save to `data/gold_dataset.json`
- [ ] Create `backend/evaluation/evaluator.py`:
  - `recall_at_k(retrieved_ids, expected_ids, k)` — fraction of expected in Top-K
  - `precision_at_k(retrieved_ids, expected_ids, k)` — fraction of Top-K that are expected
  - `evaluate_pipeline(gold_dataset, k=5)` → for each question:
    - Run retrieval (pre-reranking) → compute Recall@K, Precision@K
    - Run reranking → compute Recall@K, Precision@K on reranked set
  - Return structured report: per-question and aggregate metrics
- [ ] Create `backend/app/api/v1/endpoints/evaluation.py` — `GET /evaluation/run`:
  - Trigger evaluation on gold dataset
  - Return: `{ pre_rerank: { recall_at_k, precision_at_k }, post_rerank: { recall_at_k, precision_at_k } }`
- [ ] Production hardening:
  - [ ] Add global exception handler — catch unhandled exceptions, return `500` with `request_id`
  - [ ] Add rate limiting on `POST /query` — max 10 req/minute per IP using `slowapi`
  - [ ] Sanitize all file inputs — check MIME type with `python-magic`, not just extension
  - [ ] Enforce `MAX_UPLOAD_SIZE_MB` in upload endpoint (reject before reading full body)
  - [ ] Configure CORS: `ALLOWED_ORIGINS` from env
  - [ ] Confirm no hardcoded API keys anywhere (grep check in CI)
  - [ ] Add `HEAD /health` support
  - [ ] Add request body size limit middleware
- [ ] Create `docker-compose.yml`:
  - `backend` service: FastAPI + uvicorn
  - `frontend` service: Vite build served by nginx
  - `redis` service: `redis:7-alpine`
  - `chromadb` service: `chromadb/chroma` (or use local persistent volume)
  - Mount `data/` as volume
- [ ] Create `backend/tests/test_evaluation.py` — verify Recall@K and Precision@K computed correctly

### Frontend
- [ ] Create `EvaluationPage.jsx`:
  - Button to trigger `GET /evaluation/run`
  - Display results table: question | pre-rerank Recall@K | pre-rerank Precision@K | post-rerank Recall@K | post-rerank Precision@K
- [ ] Source grounding enhancement:
  - If chunk has `bbox` and document page image available, highlight bbox region on page thumbnail
  - Otherwise show page number + chunk type badge
- [ ] Full polish:
  - [ ] Responsive layout (mobile-friendly)
  - [ ] Error state components (network error, 4xx, 5xx messages)
  - [ ] Empty state for no documents uploaded
  - [ ] Empty state for no query results
  - [ ] Loading skeleton components
  - [ ] Toast notifications for upload success/failure

### Verification
- [ ] `GET /evaluation/run` returns `{ pre_rerank, post_rerank }` with `recall_at_k` and `precision_at_k`
- [ ] Post-rerank Recall@K ≥ pre-rerank Recall@K (reranking improves or maintains recall)
- [ ] Rate limiter blocks > 10 requests/minute from same IP on `/query`
- [ ] Upload of file > `MAX_UPLOAD_SIZE_MB` returns `413`
- [ ] Upload of unsupported MIME type returns `415`
- [ ] Server returns `request_id` in all error responses
- [ ] `docker-compose up` starts all services and health endpoint returns 200
- [ ] Frontend evaluation page shows metrics table
- [ ] `pytest backend/tests/ -v` — all tests pass
- [ ] `pytest backend/tests/test_evaluation.py` passes

---

## Summary Checklist

| Day | Focus | Key Deliverable |
|-----|-------|-----------------|
| 0 | Foundation | FastAPI skeleton, React skeleton, ChromaDB init, Redis init, all schemas |
| 1 | Upload + Jobs | `POST /documents/upload`, async ingestion, job status, frontend upload form |
| 2 | ADE + Chunking | Real ADE integration, multimodal chunks with bbox/page/type preserved |
| 3 | Embeddings + Index | OpenRouter NVIDIA embeddings, ChromaDB indexing, idempotency |
| 4 | Router + Retrieval | Query router (text/multimodal/hybrid), Top-N candidates |
| 5 | Rerank + LLM | OpenRouter reranker, context assembly, Qwen 27B + Nemotron fallback, grounded answer |
| 6 | Redis Cache | Query-answer caching, cache invalidation on re-ingestion |
| 7 | Observability | 5 benchmark categories, SQLite persistence, `/metrics` endpoint |
| 8 | Evaluation + Hardening | Recall@K / Precision@K, Docker Compose, rate limiting, full polish |
