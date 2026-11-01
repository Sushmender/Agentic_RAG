# Multimodal RAG — Implementation Plan (Day 0 + Day 1–8)

## Goal

Build a **production-oriented multimodal RAG platform** for business documents (PDF, DOCX, PPTX, XLSX, images, scanned documents).

Pipeline: **INGEST → UNDERSTAND → CHUNK → EMBED → INDEX → ROUTE → RETRIEVE → RERANK → GENERATE → GROUND → DISPLAY → MEASURE**

---

## User Review Required

> [!IMPORTANT]
> **Redis caching** will be layered over the query→answer path: a SHA-256 keyed cache (user_id + document_id + normalized_query) will store full `QueryResponse` JSON. Before running any pipeline stage, the backend checks Redis. Cache TTL will be configurable. This avoids redundant ADE, embedding, reranker, and LLM calls.

> [!IMPORTANT]
> **All NVIDIA model inference is via OpenRouter, NOT NVIDIA directly.**
> - Embedding: `nvidia/llama-nemotron-embed-vl-1b-v2` → OpenRouter
> - Reranker: `nvidia/llama-nemotron-rerank-vl-1b-v2` → OpenRouter
> - Fallback LLM: `nvidia/nemotron-3-super-120b-a12b:free` → OpenRouter
> - Primary LLM: Qwen 27B → Groq

> [!WARNING]
> **Do NOT confuse NVIDIA model name with inference provider.** All code must route NVIDIA-named models through OpenRouter API.

---

## Open Questions

> [!IMPORTANT]
> **Please clarify before execution begins:**

1. **User identity** — Should the Redis cache key include a `user_id`? If so, how is auth handled (API key header, JWT, anonymous session ID)?
2. **Cache invalidation** — When a document is re-ingested (new version), should the cache for that `document_id` be auto-invalidated?
3. **Redis deployment** — Local Redis via Docker, or managed Redis (Upstash, Redis Cloud)?
4. **ADE tier default** — Docs say DPT-3 Verity for clean docs, DPT-3 Pro for complex/scanned. Is there a user-selectable override per upload, or only automatic fallback?
5. **Evaluation gold dataset** — Do you have an existing Q&A gold set, or should the system generate a minimal one from ingested documents?
6. **Frontend auth** — Public (no auth), or should documents/queries be scoped per user session?
7. **Deployment target** — Local dev only, or does the plan need a Docker Compose / cloud deploy step?
8. **Frontend framework** — React with Vite (recommended) or Create React App?

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Python 3.11+ |
| Frontend | React + Vite |
| Document Understanding | LandingAI ADE (Parse API) |
| Vector Store | ChromaDB (persistent) |
| Embeddings | `nvidia/llama-nemotron-embed-vl-1b-v2` via OpenRouter |
| Reranker | `nvidia/llama-nemotron-rerank-vl-1b-v2` via OpenRouter |
| Primary LLM | Qwen 27B via Groq |
| Fallback LLM | `nvidia/nemotron-3-super-120b-a12b:free` via OpenRouter |
| Cache | Redis (query→answer pairs, keyed by user+doc+query) |
| Task Queue | Python asyncio (BackgroundTasks) |
| Logging | Python `structlog` structured JSON logs |

---

## Proposed Changes

### Day 0 — Foundation

#### [NEW] `backend/` — FastAPI project scaffold
- `backend/app/main.py` — FastAPI app factory
- `backend/app/api/v1/router.py` — API router aggregator
- `backend/app/api/v1/endpoints/health.py` — `/health` endpoint
- `backend/app/api/v1/endpoints/documents.py` — stub routes
- `backend/app/api/v1/endpoints/jobs.py` — stub routes
- `backend/app/api/v1/endpoints/query.py` — stub routes
- `backend/app/core/config.py` — Pydantic Settings config
- `backend/app/core/logging.py` — structlog structured logger
- `backend/app/core/errors.py` — common HTTP exception classes
- `backend/app/core/retries.py` — tenacity retry/timeout decorators
- `backend/app/schemas/document.py` — Document, DocumentMetadata Pydantic models
- `backend/app/schemas/chunk.py` — Chunk, ChunkType Pydantic models
- `backend/app/schemas/job.py` — Job, JobStatus Pydantic models
- `backend/app/schemas/query.py` — QueryRequest, QueryResponse, RetrievalResult, RerankResult, Source Pydantic models
- `backend/app/providers/base.py` — Abstract base classes: EmbeddingProvider, RerankerProvider, LLMProvider, ADEProvider
- `backend/app/providers/openrouter.py` — OpenRouter client stub
- `backend/app/providers/groq.py` — Groq client stub
- `backend/app/providers/ade.py` — LandingAI ADE client stub
- `backend/app/db/chromadb_client.py` — ChromaDB persistent client init
- `backend/app/db/redis_client.py` — Redis client init
- `backend/requirements.txt`, `backend/.env.example`, `backend/.env`
- `backend/Makefile` — dev shortcuts
- Data directories: `data/uploads/`, `data/ade_outputs/`, `data/chroma_db/`

#### [NEW] `frontend/` — React + Vite scaffold
- `frontend/src/main.jsx` — app entry
- `frontend/src/App.jsx` — root app + router
- `frontend/src/pages/DocumentsPage.jsx` — stub
- `frontend/src/pages/QueryPage.jsx` — stub
- `frontend/src/components/layout/Navbar.jsx` — stub
- `frontend/src/services/api.js` — axios client pointed at backend

---

### Day 1 — Document Upload + Async Ingestion + Jobs

#### Backend
- `POST /documents/upload` — multipart file, MIME validation, document_id generation, file storage
- `GET /documents/{document_id}` — document metadata
- `GET /jobs/{job_id}` — job status (pending/processing/completed/failed)
- `services/ingestion_service.py` — async ingestion coordinator using FastAPI BackgroundTasks
- Document idempotency: SHA-256 hash of file content → skip re-upload
- Job tracking with in-memory store (upgraded to persistent in Day 7)

#### Frontend
- Upload form (drag-and-drop + file picker)
- Ingestion status polling (job status display)
- Document list with status badges

---

### Day 2 — ADE Integration + Multimodal Chunking

#### Backend
- `providers/ade.py` — real LandingAI ADE Parse API integration (DPT-3 Verity default, DPT-3 Pro fallback)
- ADE output persistence to `data/ade_outputs/{document_id}/`
- Idempotent: skip ADE call if `data/ade_outputs/{document_id}/chunks.json` exists
- `services/chunking_service.py` — normalize ADE output into production `Chunk` schema:
  ```json
  { "chunk_id", "document_id", "chunk_type", "text", "page", "bbox", "source", "parser_version" }
  ```
- Preserve text, table, figure chunk types — NO text-only flattening
- ADE credit tracking per ingestion

---

### Day 3 — Multimodal Embeddings + ChromaDB Indexing

#### Backend
- `providers/openrouter_embedding.py` — real `nvidia/llama-nemotron-embed-vl-1b-v2` via OpenRouter
  - Passage mode for indexing, query mode for retrieval
  - Batch embedding with configurable batch size
  - Skip already-indexed chunk IDs (idempotency check against ChromaDB)
  - Retry on provider failures
  - Embedding usage/cost tracking
- `db/chromadb_client.py` — full implementation:
  - Persistent storage at `data/chroma_db/`
  - Collection: `ade_documents`
  - Metadata schema: `document_id`, `chunk_id`, `chunk_type`, `page`, `bbox_x0/y0/x1/y1`
  - Support metadata filtering by document_id, page, chunk_type
  - Idempotent upsert

---

### Day 4 — Query Router + Text/Multimodal/Hybrid Retrieval

#### Backend
- `services/query_router.py` — lightweight rule-based + keyword router:
  - `text` route: plain text questions
  - `multimodal` route: questions about tables, charts, figures, images, visual layout, scanned content
  - `hybrid` route: queries needing both
  - Avoid LLM calls for routing unless truly ambiguous
- `services/retrieval_service.py`:
  - Text retrieval: query embedding → ChromaDB similarity search (text chunks prioritized)
  - Multimodal retrieval: query embedding → ChromaDB (all chunk types, filter by type)
  - Hybrid retrieval: combine text + multimodal candidate sets, deduplicate
  - Initial recall-optimized: retrieve Top-N (configurable, default 20) candidates

---

### Day 5 — Reranking + Context Assembly + LLM Generation

#### Backend
- `providers/openrouter_reranker.py` — real `nvidia/llama-nemotron-rerank-vl-1b-v2` via OpenRouter
  - Only rerank Top-N retrieved candidates, never full collection
  - Track reranking latency and usage
- `services/context_assembly.py`:
  - Select final Top-K (default 5) after reranking
  - Deduplicate overlapping chunks
  - Preserve page/chunk/bbox provenance
  - Enforce LLM context window limits
  - Include visual evidence references when chunk_type != text
- `providers/groq.py` — real Qwen 27B via Groq
- `providers/openrouter_llm.py` — real `nvidia/nemotron-3-super-120b-a12b:free` fallback
- `services/llm_service.py`:
  - Grounded prompt: answer from evidence only
  - Instruct: cite sources, say when evidence insufficient
  - Auto-fallback from Groq → OpenRouter on failure/timeout
- `POST /query` — full end-to-end RAG query endpoint with grounded `QueryResponse`

#### Frontend
- Query input form
- Loading/streaming state
- Answer display with source citations (document, page, chunk_type, bbox)

---

### Day 6 — Redis Query Cache

#### Backend
- `db/redis_client.py` — full Redis client using `redis-py`
- `services/cache_service.py`:
  - Cache key: `SHA-256(user_id + document_id + normalize(query))`
  - Store full `QueryResponse` JSON with configurable TTL
  - Cache hit: return immediately, skip entire pipeline
  - Cache miss: run pipeline, store result before returning
  - Cache invalidation on document re-ingestion (delete by `document_id` pattern)
- Middleware or dependency injection in `/query` endpoint
- Cache hit/miss metrics in structured logs

#### Frontend
- Show cache hit indicator in UI ("⚡ Instant answer (cached)")
- Cache TTL display optional

---

### Day 7 — Observability, Telemetry, Structured Logging

#### Backend
- Structured JSON logging with `structlog` — request_id, job_id, document_id, latency per stage
- Five required operational benchmarks instrumented:
  1. End-to-end / per-stage latency (ADE, embedding, retrieval, reranking, LLM)
  2. Token usage (input/output/total)
  3. ADE credits per ingestion + cumulative
  4. Embedding cost (model, provider, token count, calculated USD)
  5. LLM cost (model, provider, input/output tokens, calculated USD)
- Persistent job store (replace in-memory with SQLite or file-based)
- `GET /metrics` — aggregated telemetry endpoint
- Retry/timeout configuration from `.env`

#### Frontend
- Telemetry panel: latency breakdown, token usage, cost estimate per query
- Document list enhanced: ADE credits used, chunk count

---

### Day 8 — RAG Evaluation + Production Hardening

#### Backend
- `evaluation/gold_dataset.py` — create/load minimal gold Q&A dataset:
  - Format: `{ "question", "expected_document_ids", "expected_chunk_ids" }`
- `evaluation/evaluator.py`:
  - Recall@K: whether expected chunks appear in Top-K retrieved
  - Precision@K: fraction of Top-K that are relevant
  - Evaluate pre-reranking and post-reranking separately
- `GET /evaluation/run` — trigger evaluation run, return Recall@K / Precision@K
- Production hardening:
  - Global exception handler
  - Rate limiting on `/query`
  - Input sanitization
  - Max file size enforcement
  - CORS configuration
  - Secret detection (no hardcoded keys)
- Docker Compose: backend + frontend + Redis + ChromaDB

#### Frontend
- Evaluation results dashboard
- Source grounding: highlight bbox on page image (if available)
- Full polish: responsive design, error states, empty states

---

## Verification Plan

### Automated Tests
```bash
pytest backend/tests/ -v
```
- Day 0: health endpoint returns 200, config loads from .env, ChromaDB initializes, Redis pings
- Day 1: upload returns document_id, job created, status transitions
- Day 2: ADE output persisted, chunks normalized with correct schema
- Day 3: embeddings generated, ChromaDB count matches chunk count, idempotency (re-run = no new embeddings)
- Day 4: router classifies text/multimodal/hybrid queries correctly, retrieval returns Top-N
- Day 5: reranker returns Top-K, LLM response includes `answer` + `sources` with page/chunk/bbox
- Day 6: cache hit on repeated query (verified via Redis key check), cache miss on new query
- Day 7: metrics endpoint returns all 5 benchmark categories
- Day 8: Recall@K ≥ 0.7 on gold dataset, Precision@K reported

### Manual Verification
- Upload a PDF, watch job status transition to `completed`
- Ask a text question → get grounded answer with source pages
- Ask a table/figure question → get answer citing table chunk with bbox
- Ask same question twice → second response is instant (cache hit)
- Pull `/metrics` and verify latency breakdown per stage
- Run evaluation endpoint and inspect Recall@K / Precision@K

---

## File Tree Summary

```
Agentic_RAG/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/v1/
│   │   │   ├── router.py
│   │   │   └── endpoints/ (health, documents, jobs, query, metrics, evaluation)
│   │   ├── core/ (config, logging, errors, retries)
│   │   ├── schemas/ (document, chunk, job, query)
│   │   ├── providers/ (base, ade, openrouter_embedding, openrouter_reranker, openrouter_llm, groq)
│   │   ├── services/ (ingestion, chunking, retrieval, query_router, context_assembly, llm, cache)
│   │   ├── db/ (chromadb_client, redis_client)
│   │   └── evaluation/ (gold_dataset, evaluator)
│   ├── tests/
│   ├── data/ (uploads/, ade_outputs/, chroma_db/)
│   ├── requirements.txt
│   ├── .env / .env.example
│   └── Makefile
├── frontend/
│   ├── src/
│   │   ├── pages/ (DocumentsPage, QueryPage, EvaluationPage)
│   │   ├── components/ (layout, documents, query, sources, telemetry)
│   │   └── services/api.js
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml
├── tasks.md
└── docs/ (existing)
```
