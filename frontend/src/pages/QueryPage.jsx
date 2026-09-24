/**
 * frontend/src/pages/QueryPage.jsx
 * Query input and results page.
 * Day 4: Full implementation — route tag, document selector, debug toggle,
 *         retrieval candidate cards.
 * Day 5: Answer box + source citations wired after LLM integration.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { documentsAPI, queryAPI } from '../services/api';
import './QueryPage.css';

/* ── Constants ────────────────────────────────────────────────────────────── */

const ROUTE_META = {
  text:        { label: 'Text',        icon: '📝', color: 'var(--route-text)' },
  multimodal:  { label: 'Multimodal',  icon: '🖼️',  color: 'var(--route-mm)' },
  hybrid:      { label: 'Hybrid',      icon: '⚡',  color: 'var(--route-hybrid)' },
};

const CHUNK_TYPE_META = {
  text:    { icon: '📄', label: 'Text',    color: '#6366f1' },
  table:   { icon: '📊', label: 'Table',   color: '#10b981' },
  figure:  { icon: '🖼️', label: 'Figure',  color: '#f59e0b' },
};

/* ── Main component ───────────────────────────────────────────────────────── */

export default function QueryPage() {
  const [query, setQuery]           = useState('');
  const [documents, setDocuments]   = useState([]);
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [loading, setLoading]       = useState(false);
  const [result, setResult]         = useState(null);   // QueryResponse
  const [error, setError]           = useState(null);
  const [showDebug, setShowDebug]   = useState(false);
  const [docsLoading, setDocsLoading] = useState(true);
  const textareaRef = useRef(null);

  /* Load completed documents for the document selector */
  useEffect(() => {
    setDocsLoading(true);
    documentsAPI.list()
      .then(res => {
        const completed = (res.data || []).filter(d => d.status === 'completed');
        setDocuments(completed);
      })
      .catch(() => setDocuments([]))
      .finally(() => setDocsLoading(false));
  }, []);

  /* Auto-resize textarea */
  const handleQueryChange = (e) => {
    setQuery(e.target.value);
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = `${Math.min(ta.scrollHeight, 240)}px`;
    }
  };

  /* Toggle a document in/out of the selection filter */
  const toggleDoc = useCallback((docId) => {
    setSelectedDocs(prev =>
      prev.includes(docId) ? prev.filter(id => id !== docId) : [...prev, docId]
    );
  }, []);

  /* Submit query */
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim() || loading) return;

    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const payload = {
        query: query.trim(),
        document_ids: selectedDocs.length > 0 ? selectedDocs : null,
      };
      const res = await queryAPI.query(payload);
      setResult(res.data);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Query failed.';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  /* Keyboard shortcut: Ctrl+Enter submits */
  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleSubmit(e);
  };

  return (
    <div className="query-page">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="page-header">
        <h1 className="page-title">💬 Ask a Question</h1>
        <p className="page-subtitle">
          Query your documents using multimodal RAG — text, tables, figures, and images.
        </p>
      </div>

      {/* ── Query form ─────────────────────────────────────────────────── */}
      <form className="query-form" onSubmit={handleSubmit}>

        {/* Document selector */}
        {!docsLoading && documents.length > 0 && (
          <div className="doc-selector">
            <label className="doc-selector-label">
              🗂️ Filter to specific documents{' '}
              <span className="doc-selector-hint">(leave empty to search all)</span>
            </label>
            <div className="doc-chips">
              {documents.map(doc => (
                <button
                  key={doc.document_id}
                  type="button"
                  className={`doc-chip ${selectedDocs.includes(doc.document_id) ? 'doc-chip--active' : ''}`}
                  onClick={() => toggleDoc(doc.document_id)}
                  title={doc.document_id}
                >
                  {doc.filename}
                  {selectedDocs.includes(doc.document_id) && <span className="chip-check">✓</span>}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Textarea */}
        <div className="query-input-wrapper">
          <textarea
            ref={textareaRef}
            id="query-input"
            className="query-input"
            placeholder="Ask anything about your documents…&#10;e.g. 'What was the revenue in Q3?' or 'Show me the sales table'"
            value={query}
            onChange={handleQueryChange}
            onKeyDown={handleKeyDown}
            rows={3}
            disabled={loading}
            aria-label="Query input"
          />
          <span className="query-shortcut-hint">Ctrl+Enter to submit</span>
        </div>

        {/* Submit row */}
        <div className="query-form-footer">
          <button
            id="query-submit-btn"
            type="submit"
            className="query-btn"
            disabled={loading || !query.trim()}
          >
            {loading
              ? <><span className="spinner" /> Searching…</>
              : <><span>🔍</span> Ask Question</>
            }
          </button>

          {result && (
            <button
              type="button"
              className="debug-toggle-btn"
              onClick={() => setShowDebug(v => !v)}
            >
              {showDebug ? '🔒 Hide' : '🔓 Show'} raw candidates
            </button>
          )}
        </div>
      </form>

      {/* ── Error ──────────────────────────────────────────────────────── */}
      {error && (
        <div className="query-error" role="alert">
          <span className="error-icon">⚠️</span>
          <span>{typeof error === 'string' ? error : JSON.stringify(error)}</span>
        </div>
      )}

      {/* ── Loading skeleton ───────────────────────────────────────────── */}
      {loading && <QuerySkeleton />}

      {/* ── Results ────────────────────────────────────────────────────── */}
      {!loading && result && (
        <div className="query-results">

          {/* Route tag + latency */}
          <div className="result-meta-row">
            <RouteTag route={result.route_type} />
            <span className="result-latency">
              ⏱ {result.latency?.total_ms?.toFixed(0) ?? '—'} ms
            </span>
            <span className="result-count">
              {result.sources.length} candidate{result.sources.length !== 1 ? 's' : ''}
            </span>
          </div>

          {/* Answer box — Day 4 shows placeholder; Day 5 shows real answer */}
          <AnswerBox answer={result.answer} isPlaceholder={!result.model_used} />

          {/* Source cards (always shown) */}
          {result.sources.length > 0 && (
            <div className="sources-section">
              <h3 className="sources-heading">
                📎 Retrieved Chunks
                <span className="sources-subhead">sorted by similarity score</span>
              </h3>
              <div className="source-cards">
                {result.sources.map((src, idx) => (
                  <SourceCard key={src.chunk_id} source={src} rank={idx + 1} />
                ))}
              </div>
            </div>
          )}

          {/* Debug panel */}
          {showDebug && (
            <DebugPanel sources={result.sources} route={result.route_type} latency={result.latency} />
          )}

          {/* Empty candidates */}
          {result.sources.length === 0 && (
            <div className="empty-state">
              <span className="empty-icon">🔍</span>
              <p>No matching chunks found. Try a different question or upload more documents.</p>
            </div>
          )}
        </div>
      )}

      {/* ── Initial empty state ────────────────────────────────────────── */}
      {!loading && !result && !error && (
        <div className="query-results">
          <div className="empty-state">
            <span className="empty-icon">💡</span>
            <p>Ask a question to get grounded answers with source citations.</p>
            <p className="empty-hint">
              Tip: Use words like <em>table</em>, <em>chart</em>, or <em>figure</em> to trigger multimodal retrieval.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Sub-components ───────────────────────────────────────────────────────── */

function RouteTag({ route }) {
  const meta = ROUTE_META[route] || ROUTE_META.text;
  return (
    <span className="route-tag" style={{ '--tag-color': meta.color }}>
      {meta.icon} {meta.label}
    </span>
  );
}

function AnswerBox({ answer, isPlaceholder }) {
  return (
    <div className={`answer-box ${isPlaceholder ? 'answer-box--placeholder' : ''}`}>
      {isPlaceholder && (
        <div className="answer-placeholder-badge">
          ⏳ Retrieval only — answer generation coming in next pipeline stage
        </div>
      )}
      <p className="answer-text">{answer}</p>
    </div>
  );
}

function SourceCard({ source, rank }) {
  const [expanded, setExpanded] = useState(false);
  const typeMeta = CHUNK_TYPE_META[source.chunk_type] || CHUNK_TYPE_META.text;

  return (
    <div className="source-card" id={`source-card-${source.chunk_id}`}>
      <div className="source-card-header" onClick={() => setExpanded(v => !v)}>
        <span className="source-rank">#{rank}</span>
        <span
          className="source-type-badge"
          style={{ '--badge-color': typeMeta.color }}
        >
          {typeMeta.icon} {typeMeta.label}
        </span>
        <span className="source-page">Page {source.page + 1}</span>
        <span className="source-score">
          {(source.relevance_score * 100).toFixed(1)}% match
        </span>
        <span className="source-expand-icon">{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <div className="source-card-body">
          <p className="source-preview">{source.text_preview || '(no preview)'}</p>
          <div className="source-meta-grid">
            <span className="source-meta-item">
              <strong>Chunk ID</strong>
              <code>{source.chunk_id.slice(0, 16)}…</code>
            </span>
            <span className="source-meta-item">
              <strong>Doc ID</strong>
              <code>{source.document_id.slice(0, 12)}…</code>
            </span>
            {source.bbox?.length === 4 && (
              <span className="source-meta-item">
                <strong>BBox</strong>
                <code>[{source.bbox.map(v => v.toFixed(2)).join(', ')}]</code>
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DebugPanel({ sources, route, latency }) {
  return (
    <div className="debug-panel">
      <h4 className="debug-heading">🔬 Raw Retrieval Debug</h4>
      <div className="debug-latency-row">
        <span>Embed: <strong>{latency?.query_embed_ms?.toFixed(0) ?? '—'} ms</strong></span>
        <span>Retrieve: <strong>{latency?.retrieval_ms?.toFixed(0) ?? '—'} ms</strong></span>
        <span>Route: <strong>{route}</strong></span>
      </div>
      <div className="debug-table-wrapper">
        <table className="debug-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Chunk ID</th>
              <th>Type</th>
              <th>Page</th>
              <th>Score</th>
              <th>Preview</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((src, i) => (
              <tr key={src.chunk_id}>
                <td>{i + 1}</td>
                <td><code title={src.chunk_id}>{src.chunk_id.slice(0, 10)}…</code></td>
                <td>{src.chunk_type}</td>
                <td>{src.page + 1}</td>
                <td>{(src.relevance_score * 100).toFixed(1)}%</td>
                <td className="debug-preview">{src.text_preview?.slice(0, 60) || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function QuerySkeleton() {
  return (
    <div className="query-skeleton" aria-label="Loading…">
      <div className="skeleton-meta-row">
        <div className="skeleton-tag" />
        <div className="skeleton-latency" />
      </div>
      <div className="skeleton-answer" />
      <div className="skeleton-cards">
        {[1, 2, 3].map(i => <div key={i} className="skeleton-card" />)}
      </div>
    </div>
  );
}
