# Multimodal RAG — Demo Guide

A single-page walkthrough for evaluators and new developers.

---

## Starting the App

**Backend** (from the `backend/` directory):
```bash
make dev
```
This runs `python run.py`, which starts the FastAPI server on `http://127.0.0.1:8000`.
Override host or port: `make dev HOST=0.0.0.0 PORT=9000`.

**Frontend** (from the `frontend/` directory):
```bash
npm run dev
```
Opens the React app on `http://localhost:5173`.

---

## First-Time Setup

1. Open `http://localhost:5173` in your browser.
2. Click **Create one** on the login page to register a new account.
3. On the Documents page, upload a file from `backend/sample_docs/` (e.g. one of the PDFs or the `.docx` files).
4. Wait for the ingestion job to complete (the status badge on the document card will turn green).

---

## 5-Step Demo Script

### 1 — Documents
- After uploading, the **Documents** page shows your file with its status, chunk count, and page count.
- Click a document card to expand the details panel.

### 2 — Query with a Citation Click
- Navigate to **Query** (`/query`).
- Ask a question about your uploaded document (e.g. *"What are the key findings?"*).
- The answer appears with `[Source N]` citation chips.
- Click a citation chip → the matching page image scrolls into view with the relevant region highlighted in a coloured bounding box.

### 3 — Second Chat Tab and Follow-Up
- Click **+** in the chat tab strip to open a second chat tab.
- Ask a follow-up question in the new tab; the two conversations stay independent.
- Switch between tabs — each retains its own history.

### 4 — Metrics
- Navigate to **Metrics** (`/metrics`).
- The dashboard shows per-stage latency bars, cache hit rate, cost estimates, and a recent-queries table.
- Use the **Today / Yesterday / This week** tabs to filter, or click **Refresh** for the latest data.

### 5 — Command Palette and Shortcuts
- Press **Ctrl+K** (or **⌘K** on macOS) to open the command palette — jump to any page by typing its name.
- Press **?** to open the keyboard shortcuts modal.

