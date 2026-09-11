# Multimodal RAG — CLI Implementation Brief

## 0. Goal

Build a **production-oriented multimodal RAG application** for general business documents.

Supported inputs:
- PDF
- DOCX
- PPTX
- XLSX
- Images
- Scanned documents
- Similar business-document formats

The system must support **text, multimodal, and hybrid retrieval**, and intelligently decide which path a query needs.

### Stack

- Backend: FastAPI
- Frontend: React
- Document preprocessing: LandingAI ADE
- Vector DB: ChromaDB
- Embedding: `nvidia/llama-nemotron-embed-vl-1b-v2`
- Reranker: `nvidia/llama-nemotron-rerank-vl-1b-v2`
- Fallback LLM: `nvidia/nemotron-3-super-120b-a12b:free`
- NVIDIA-model inference provider: **OpenRouter**
- Primary LLM if retained: Qwen 27B via Groq

## 1. CRITICAL PROVIDER RULE

**NVIDIA is the model developer/name, NOT the inference provider.**

Use:

| Component | Model | Inference |
|---|---|---|
| Embedding | `nvidia/llama-nemotron-embed-vl-1b-v2` | OpenRouter |
| Reranker | `nvidia/llama-nemotron-rerank-vl-1b-v2` | OpenRouter |
| Fallback LLM | `nvidia/nemotron-3-super-120b-a12b:free` | OpenRouter |
| Primary LLM | Qwen 27B | Groq |

Keep provider/model integrations behind abstractions so they can be replaced easily.

---

# 2. SYSTEM FLOW

```text
Documents
  ↓
Upload + Validation
  ↓
Async Ingestion
  ↓
LandingAI ADE Parse
  ↓
Structured Multimodal Chunks
  ↓
OpenRouter Multimodal Embeddings
  ↓
ChromaDB
  ↓
User Query
  ↓
Query Router
  ↓
Text / Multimodal / Hybrid Retrieval
  ↓
Top-N Candidates
  ↓
OpenRouter Multimodal Reranker
  ↓
Top-K Context
  ↓
LLM
  ↓
Grounded Answer + Sources
  ↓
React UI
```

---

# 3. DOCUMENT INGESTION

Create an ingestion service that:

1. Accepts supported file types.
2. Validates MIME type and size.
3. Creates a unique `document_id`.
4. Stores the original document.
5. Creates an asynchronous ingestion job.
6. Tracks `pending / processing / completed / failed`.
7. Prevents duplicate processing of the same document/version.

Maintain metadata such as:

```text
document_id
filename
document_type
version
created_at
status
source
parser_version
```

Do expensive processing outside the synchronous upload request.

---

# 4. LANDINGAI ADE

Use **LandingAI ADE Parse** as the document-understanding layer.

Reference notebook flow:

```text
Document → ADE → structured chunks → embeddings → ChromaDB
```

The notebook represents chunks using:

```text
chunk_id
chunk_type
text
bbox
page
```

Production chunks should additionally retain document/provenance data:

```json
{
  "chunk_id": "...",
  "document_id": "...",
  "chunk_type": "text|table|figure",
  "text": "...",
  "page": 0,
  "bbox": [x0, y0, x1, y1],
  "source": "...",
  "parser_version": "..."
}
```

Persist ADE results. Do not repeatedly parse the same document.

### ADE cost strategy

- Default: **DPT-3 Verity** for clean/digital documents.
- Fallback: **DPT-3 Pro** for difficult scans, handwriting, complex figures/charts, or poor parsing quality.
- Reuse persisted ADE output for experiments.

---

# 5. MULTIMODAL CHUNKING

Do **not** convert everything into plain text.

Preserve:

- Text
- Tables
- Figures
- Charts
- Images
- Scanned/visual content

Every chunk must retain:

```text
document_id
chunk_id
chunk_type
page
bbox
text/description
source
```

The original notebook already demonstrates page, chunk-type and bbox metadata. Extend this instead of removing it.

---

# 6. MULTIMODAL EMBEDDINGS

Model:

`nvidia/llama-nemotron-embed-vl-1b-v2`

Provider:

**OpenRouter**

Requirements:

- Support multimodal document/query representation.
- Use correct passage/query mode.
- Batch embedding calls.
- Avoid duplicate embeddings.
- Store model/version information.
- Retry provider failures.
- Track embedding usage/cost.

Store embeddings and metadata in **ChromaDB**.

---

# 7. CHROMADB

ChromaDB is the vector store.

Store:

```text
chunk_id
embedding
content
metadata
```

Metadata should include:

```text
document_id
chunk_id
chunk_type
page
bbox_x0
bbox_y0
bbox_x1
bbox_y1
```

Use persistent storage.

Use stable chunk IDs and idempotent indexing so already-indexed chunks are not inserted again.

Support metadata filtering by document, page, and chunk type.

---

# 8. QUERY ROUTER

Before retrieval, determine the evidence type required.

### Text route
Normal textual questions.

### Multimodal route
Questions requiring:
- Tables
- Charts
- Figures
- Images
- Visual layout
- Scanned content

### Hybrid route
Questions where both text and visual evidence may matter.

Keep routing lightweight. Avoid using a large LLM merely to classify every query if simple rules/features are enough.

---

# 9. RETRIEVAL

Initial retrieval should optimize for **recall**.

```text
Query
 ↓
Query Embedding
 ↓
ChromaDB
 ↓
Candidate Set
```

Text queries should use textual evidence where sufficient.

Multimodal queries should retrieve multimodal evidence.

Hybrid queries can combine relevant candidate signals.

Do not make the candidate set too small because the reranker needs enough candidates to choose from.

---

# 10. MULTIMODAL RERANKING

Model:

`nvidia/llama-nemotron-rerank-vl-1b-v2`

Provider:

**OpenRouter**

Flow:

```text
ChromaDB Top-N
   ↓
Multimodal Reranker
   ↓
Final Top-K
```

Only rerank retrieved candidates.

Never rerank the entire document collection.

Track reranking latency and usage.

---

# 11. CONTEXT ASSEMBLY

After reranking:

1. Select final Top-K evidence.
2. Remove unnecessary duplicates.
3. Preserve provenance.
4. Keep context within the LLM limit.
5. Include visual evidence when needed.
6. Preserve page/chunk/bbox references.

Never send the entire document to the LLM unless there is a specific reason.

Optimize context because excessive context increases latency, token usage, cost, and noise.

---

# 12. LLM GENERATION

Primary LLM if retained:

```text
Qwen 27B → Groq
```

Fallback:

```text
nvidia/nemotron-3-super-120b-a12b:free → OpenRouter
```

LLM requirements:

- Answer from retrieved evidence.
- Avoid unsupported claims.
- Say when evidence is insufficient.
- Return source references.
- Preserve page/document grounding.

Keep LLM access behind a provider interface.

---

# 13. GROUNDED RESPONSE

API response should contain something like:

```json
{
  "answer": "...",
  "sources": [
    {
      "document_id": "...",
      "chunk_id": "...",
      "page": 12,
      "bbox": [0.1, 0.2, 0.8, 0.5],
      "chunk_type": "table"
    }
  ]
}
```

The final answer must be traceable back to the source evidence.

Goal:

**Answer + exactly where the answer came from.**

---

# 14. FASTAPI

Suggested endpoints:

```text
POST /documents/upload
GET  /documents/{document_id}
GET  /jobs/{job_id}
POST /query
GET  /documents/{document_id}/chunks/{chunk_id}
```

Suggested structure:

```text
api/
services/
models/
schemas/
ingestion/
retrieval/
providers/
evaluation/
utils/
```

Routes should not contain provider/model business logic.

---

# 15. REACT

Minimum UI:

### Documents
- Upload
- Ingestion status
- Document list

### Query
- Ask question
- Loading state
- Answer

### Sources
- Document
- Page
- Chunk type
- Visual/page grounding

Do not over-engineer the UI before the backend pipeline works.

---

# 16. PRODUCTION ENGINEERING

Implement:

- Async ingestion
- Retries
- Timeouts
- Error handling
- Caching
- Idempotency
- Structured logging
- Request/job IDs
- Document versioning
- Environment configuration
- Secret protection
- Model/provider abstraction

Never hardcode API keys.

---

# 17. COST + PERFORMANCE

Optimize:

### ADE
Parse once and reuse.

### Embeddings
Batch requests and skip existing chunks.

### Retrieval
Use ChromaDB for efficient candidate retrieval.

### Reranking
Only rerank Top-N.

### LLM
Send only relevant context.

### Routing
Avoid multimodal processing when text-only is enough.

### Caching
Cache reusable computations where appropriate.

Target:

**good quality + low latency + controlled cost.**

---

# 18. REQUIRED OPERATIONAL BENCHMARKS

Track exactly these five:

### 1. Latency
- End-to-end
- ADE
- Embedding
- Retrieval
- Reranking
- LLM

### 2. Token Usage
- Input
- Output
- Total

### 3. ADE Credits
- Per ingestion
- Total consumption

### 4. Embedding Cost
- Usage
- Model
- Provider
- Calculated cost

### 5. LLM Cost
- Model
- Provider
- Input/output tokens
- Calculated cost

Make telemetry structured so different configurations can be compared.

---

# 19. REQUIRED RAG EVALUATION

After the complete RAG pipeline works, create a small gold dataset containing:

```text
question
expected relevant document/chunk
```

Measure only:

### Recall@K
Whether relevant evidence appears in Top-K.

### Precision@K
How much of Top-K evidence is actually relevant.

Evaluate:

```text
Initial Retrieval → Recall@K / Precision@K
       ↓
Reranking
       ↓
Final Retrieval → Recall@K / Precision@K
```

Do not introduce additional evaluation metrics unless requested.

---

# 20. BUILD ORDER

Implement in this order:

```text
1. Project structure
2. FastAPI skeleton
3. Document upload
4. Async ingestion/jobs
5. ADE integration
6. Chunk normalization
7. OpenRouter multimodal embeddings
8. ChromaDB indexing
9. Basic retrieval
10. Query router
11. Multimodal/hybrid retrieval
12. OpenRouter multimodal reranking
13. Context assembly
14. LLM + fallback
15. Source/page/bbox grounding
16. React UI
17. Logging + telemetry
18. Cost/latency benchmarks
19. Gold evaluation dataset
20. Recall@K + Precision@K
21. Production hardening
```

---

# 21. NON-NEGOTIABLE CLI RULES

1. **Do not blindly copy the notebook.** It is the baseline/reference.
2. **Do not build text-only RAG.**
3. **Do not confuse NVIDIA models with NVIDIA inference.** NVIDIA is the model name/developer; **OpenRouter is the inference provider** for the specified NVIDIA models.
4. Preserve multimodal information.
5. Preserve page/bbox/chunk provenance.
6. Avoid unnecessary LLM calls.
7. Avoid unnecessary ADE calls.
8. Do not rerank the entire database.
9. Do not send entire documents to the LLM.
10. Keep providers/models replaceable.
11. Track the five required operational benchmarks.
12. Evaluate using Recall@K and Precision@K.
13. Backend correctness comes before UI polish.
14. Prefer deterministic/rule-based logic when an LLM is unnecessary.
15. Every generated answer must be grounded in retrieved evidence.

## FINAL DEFINITION OF DONE

The finished system must reliably perform:

**INGEST → UNDERSTAND → CHUNK → EMBED → INDEX → ROUTE → RETRIEVE → RERANK → GENERATE → GROUND → DISPLAY → MEASURE**

This is a **production-oriented multimodal RAG platform**, not just a notebook demo.
