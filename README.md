# Multimodal RAG Platform

A production-grade **Retrieval-Augmented Generation (RAG)** system that understands documents visually — not just text. Powered by LandingAI ADE for multimodal parsing, NVIDIA embeddings for semantic indexing, and Groq / OpenRouter for grounded answer generation.

## Key Features

- **Multimodal document understanding** — parses PDF, DOCX, PPTX, XLSX, and images; preserves tables, figures, and bounding boxes
- **Intelligent query routing** — automatically routes text, multimodal, or hybrid queries
- **Source grounding** — answers cite specific document pages with bbox highlights
- **Redis query cache** — instant repeat answers with per-user cache isolation
- **Full observability** — latency breakdown, token counts, cost tracking per query
- **RAG evaluation** — Recall@K / Precision@K pre- and post-reranking

---

## Architecture

```
[Upload] -> [LandingAI ADE] -> [Chunk Normalize] -> [NVIDIA Embed] -> [ChromaDB]

[Query] -> [Redis cache?] -> [Router] -> [ChromaDB Top-N] -> [NVIDIA Reranker]
        -> [Context Assembly] -> [Groq Qwen 27B / Nemotron 120B fallback]
        -> [Grounded Answer + Source Citations]
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn |
| Frontend | React 18 + Vite |
| Document Parsing | LandingAI ADE (dpt-2-latest / dpt-3-pro) |
| Embeddings | OpenRouter - nvidia/llama-nemotron-embed-vl-1b-v2 |
| Reranker | OpenRouter - nvidia/llama-nemotron-rerank-vl-1b-v2 |
| Primary LLM | Groq - Qwen3.8 27B |
| Fallback LLM | OpenRouter - Nemotron 120B |
| Vector Store | ChromaDB (persistent, embedded) |
| Cache | Redis / Upstash Redis |
| Persistent Store | SQLite via aiosqlite |
| Auth | JWT (python-jose) |
| Logging | structlog (structured JSON) |
| MIME Validation | python-magic (magic-byte inspection) |

---

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- Redis (local or Upstash free tier)
- API keys: LandingAI, OpenRouter, Groq

---

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend: http://localhost:8000 | Docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
# VITE_API_BASE_URL=http://localhost:8000/api/v1
npm run dev
```

Frontend: http://localhost:5173

---

## Environment Variables

| Variable | Description |
|---|---|
| LANDINGAI_API_KEY | LandingAI ADE API key |
| ADE_MODEL | dpt-2-latest or dpt-3-pro |
| OPENROUTER_API_KEY | OpenRouter API key |
| GROQ_API_KEY | Groq API key |
| REDIS_URL | Redis URL (redis:// or rediss:// for Upstash) |
| JWT_SECRET_KEY | Secret for JWT signing (change in prod!) |
| MAX_UPLOAD_SIZE_MB | Upload size limit (default: 50) |
| CACHE_TTL_SECONDS | Redis cache TTL (default: 3600) |
| RETRIEVAL_TOP_N | Candidates for reranker (default: 20) |
| RERANK_TOP_K | Final chunks for LLM context (default: 5) |
| ALLOWED_ORIGINS | CORS origins (comma-separated) |

---

## API Endpoints

### Health
- GET /api/v1/health — service health
- HEAD /api/v1/health — uptime check

### Auth
- POST /api/v1/auth/register — create account
- POST /api/v1/auth/login — get JWT token

### Documents
- POST /api/v1/documents/upload — upload document
- GET /api/v1/documents/ — list documents
- GET /api/v1/documents/{id} — document metadata
- GET /api/v1/documents/{id}/chunks/{chunk_id} — get chunk

### Jobs
- GET /api/v1/jobs/{job_id} — poll ingestion status

### Query
- POST /api/v1/query — full RAG pipeline

### Observability
- GET /api/v1/metrics — aggregate metrics
- GET /api/v1/evaluation/run — run RAG evaluation

---

## Running Tests

```bash
cd backend
.venv\Scripts\activate
pytest tests/ -v
```

---

## Project Structure

```
Agentic_RAG/
|-- backend/
|   |-- app/
|   |   |-- api/v1/endpoints/    # FastAPI route handlers
|   |   |-- core/                # Config, logging, security, errors
|   |   |-- db/                  # ChromaDB, Redis, SQLite clients
|   |   |-- evaluation/          # Recall@K / Precision@K evaluator
|   |   |-- providers/           # LandingAI, OpenRouter, Groq clients
|   |   |-- schemas/             # Pydantic models
|   |   |-- services/            # Ingestion, embedding, retrieval, LLM, cache
|   |   `-- main.py
|   |-- data/                    # uploads, ade_outputs, chroma_db (gitignored)
|   |-- tests/                   # pytest test suites
|   `-- requirements.txt
|-- frontend/
|   `-- src/
|       |-- components/          # Layout, UI, query, documents, sources
|       |-- context/             # AuthContext (JWT)
|       |-- pages/               # Documents, Query, Metrics, Evaluation, Auth
|       `-- services/api.js      # Axios client
|-- tasks.md
`-- README.md
```

---

## Ingestion Pipeline

```
Upload -> SHA-256 dedup -> Save file -> ADE parse
-> Chunk normalization (type/bbox/page preserved)
-> NVIDIA embeddings (batch=16)
-> ChromaDB upsert (idempotent)
-> SQLite metadata update
```

## Query Pipeline

```
Query -> Redis cache check
-> Query router (text | multimodal | hybrid)
-> Embed query (NVIDIA)
-> ChromaDB cosine similarity Top-20
-> NVIDIA Reranker Top-5
-> Context assembly (8000 token budget)
-> Groq Qwen 27B -> fallback Nemotron 120B
-> Grounded answer + [Source N] citations
-> Redis cache store
-> Return answer + sources + latency breakdown
```

---

## Feature Timeline

| Day | Feature | Status |
|---|---|---|
| 0 | Foundation (FastAPI, React, ChromaDB, Redis) | Done |
| 1 | Document upload + async ingestion + job tracking | Done |
| 2 | LandingAI ADE integration + multimodal chunk normalization | Done |
| 3 | NVIDIA embeddings + ChromaDB indexing | Done |
| 4 | Query router (text/multimodal/hybrid) + retrieval | Done |
| 5 | NVIDIA reranker + context assembly + Groq/Nemotron LLM | Done |
| 6 | Redis query-answer cache with user isolation | Done |
| 7 | Observability (5 benchmark categories, SQLite persistence) | Done |
| 8 | RAG evaluation (Recall@K, Precision@K) + source grounding | Done |
| 9 | Production hardening (magic-byte MIME, sonner toasts, error states) | Done |
