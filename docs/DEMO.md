# Multimodal Agentic RAG — Demo Guide

A concise guide for launching and demonstrating the Multimodal Agentic RAG application.

---

## 1. Starting the Application

Ensure prerequisite environment variables are set in `backend/.env`.

### Backend
From the repository root, start the FastAPI server:
```bash
cd backend
make dev
```
*Defaults to `http://127.0.0.1:8000` with hot reload enabled.*

### Frontend
From a separate terminal:
```bash
cd frontend
npm run dev
```
*Opens the web workspace at `http://localhost:5173`.*

---

## 2. Demo Accounts & Data Ownership

The system enforces strict multi-tenant isolation across SQLite, ChromaDB, ADE outputs, Redis cache, and telemetry.

| Account Username | Owned Documents | Chunks |
| :--- | :--- | :---: |
| **`test`** | `Agentic_AI_Coding_Interview_Questions_and_Answers.docx` | 88 chunks |
| **`test2`** | `5_long_annual_report.pdf`<br>`1_text_policy_memo.docx` | 8 chunks<br>7 chunks |

*(Use the passwords established during your local environment onboarding. Never commit credentials to version control.)*

---

## 3. Five-Step Demonstration Script

### Step 1 · Documents Workspace & Isolation
1. Log in as user **`test`**.
2. Navigate to **Documents** in the sidebar.
3. Observe that only `Agentic_AI_Coding_Interview_Questions_and_Answers.docx` is displayed, along with parsing status and chunk count (88 chunks).
4. Notice that documents owned by `test2` (`5_long_annual_report.pdf` and `1_text_policy_memo.docx`) are completely hidden.

### Step 2 · Query & Grounded Evidence
1. Navigate to **Chat / Query**.
2. Ask: *"What are the key responsibilities of an Agentic AI Engineer?"*
3. Watch the assistant response stream in with numbered citation badges (e.g. `[1]`).
4. Click citation `[1]`:
   - The right-hand **Evidence Panel** immediately brings the corresponding source card into view and highlights it.
   - For visual documents (PDFs/images), switch to the **Page** view to see the exact bounding box overlay on the rendered document page.
5. In the sources list, observe that low-relevance sources (< 5%) are cleanly collapsed under a *"Show N low-relevance sources"* row, keeping the interface uncluttered while retaining instant click-to-expand citation support.

### Step 3 · Multi-Tab Chat Workflows
1. Click the **`+`** icon on the Chat Tab Strip to open a new tab.
2. Note that each tab maintains its own independent conversation history, active document filters, model selection, and composer draft.
3. Use the document filter dropdown to restrict a query to specific owned documents, or leave it blank to query all owned documents.

### Step 4 · User-Scoped Telemetry & Metrics
1. Navigate to **Metrics** in the sidebar.
2. Review the caller-scoped dashboard:
   - Query and ingestion counts.
   - Stage-by-stage latency breakdowns (Embedding, Retrieval, Reranking, LLM).
   - Cache hit rate and total token/cost tracking.
   - ADE credit usage.
   - Recent queries table (strictly filtered to the active user).

### Step 5 · Command Palette & Keyboard Shortcuts
1. Press `Ctrl + K` (or `Cmd + K` on macOS) anywhere in the application.
2. Use the Command Palette to navigate across pages (*Documents*, *Chat*, *Evaluation*, *Metrics*), switch chat tabs, or trigger actions without touching the mouse.
3. Press `?` or open the shortcuts modal to review all available hotkeys.
