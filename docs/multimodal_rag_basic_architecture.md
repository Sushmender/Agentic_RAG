# Multimodal RAG — Basic Architecture

```text
                    DOCUMENTS
                       │
       ┌───────────────┼────────────────┐
       ↓               ↓                ↓
      PDF             DOCX             XLSX
       ↓               ↓                ↓
       └───────────────┼────────────────┘
                       ↓
                 LANDINGAI ADE
                       │
                       ↓
           Understand the document
                       │
        ┌──────────────┼──────────────┐
        ↓              ↓              ↓
      TEXT           TABLE          IMAGE
        │              │              │
        └──────────────┼──────────────┘
                       ↓
             Chunks + Metadata
                       │
             page / bbox / type
                       │
                       ↓
          NVIDIA Multimodal Embedding
        llama-nemotron-embed-vl-1b-v2
                       │
                       ↓
                    CHROMADB
                       │
                       │
             USER ASKS QUESTION
                       │
                       ↓
                 QUERY ROUTER
                       │
              ┌────────┴────────┐
              ↓                 ↓
        Text Retrieval     Multimodal
                            Retrieval
              └────────┬────────┘
                       ↓
                  TOP CANDIDATES
                       │
                       ↓
             NVIDIA Multimodal
                  RERANKER
        llama-nemotron-rerank-vl-1b-v2
                       │
                       ↓
                 BEST CONTEXT
                       │
                       ↓
                 QWEN 27B
                 via Groq
                       │
                fallback ↓
             Nemotron 120B
              via OpenRouter
                       │
                       ↓
                  FINAL ANSWER
                       │
              ┌────────┴────────┐
              ↓                 ↓
          Answer             Sources
                              Page
                              Chunk
                              Grounding
```

## Provider clarification

The NVIDIA names above refer to the **models**, not the inference provider.

- `nvidia/llama-nemotron-embed-vl-1b-v2` → inference via **OpenRouter**
- `nvidia/llama-nemotron-rerank-vl-1b-v2` → inference via **OpenRouter**
- Qwen 27B → inference via **OpenRouter**
- Nemotron 120B fallback → inference via **OpenRouter**
