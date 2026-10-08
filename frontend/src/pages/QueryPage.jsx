/**
 * frontend/src/pages/QueryPage.jsx
 * Query input and results page.
 * Day 5: Full pipeline — real answer, provider selector dropdown,
 *         model badge, reranker count, latency breakdown, source citations.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'sonner';
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

const PROVIDER_OPTIONS = [
  { value: 'groq',        label: 'Groq — Qwen 3.8 27B',     icon: '⚡' },
  { value: 'openrouter',  label: 'OpenRouter — Nemotron 120B', icon: '🔮' },
];

/* ── Main component ───────────────────────────────────────────────────────── */

export default function QueryPage() {
  const [query, setQuery]               = useState('');
  const [documents, setDocuments]       = useState([]);
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [provider, setProvider]         = useState('groq');
  const [loading, setLoading]           = useState(false);
  const [result, setResult]             = useState(null);   // QueryResponse
  const [error, setError]               = useState(null);
  const [showDebug, setShowDebug]       = useState(false);
  const [docsLoading, setDocsLoading]   = useState(true);
  const [docsError, setDocsError]       = useState(false);
  const textareaRef = useRef(null);
  const navigate = useNavigate();

  /* Load completed documents for the document selector */
  useEffect(() => {
    setDocsLoading(true);
    documentsAPI.list()
      .then(res => {
        const completed = (res.data.documents || res.data || []).filter(d => d.status === 'completed');
        setDocuments(completed);
        setDocsError(false);
      })
      .catch(() => {
        setDocuments([]);
        setDocsError(true);
      })
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
        query:        query.trim(),
        document_ids: selectedDocs.length > 0 ? selectedDocs : null,
        llm_provider: provider,
      };
      const res = await queryAPI.query(payload);
      setResult(res.data);
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail || err.message || 'Query failed.';
      if (status === 429) {
        const msg = 'Rate limit reached. Please wait a moment before trying again.';
        setError(msg);
        toast.warning(msg);
      } else if (status >= 500) {
        const msg = `Server error: ${detail}`;
        setError(msg);
        toast.error(msg);
      } else {
        setError(detail);
        toast.error(detail);
      }
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

      {/* ── No documents CTA ───────────────────────────────────────────── */}
      {!docsLoading && !docsError && documents.length === 0 && (
        <div className="query-no-docs-banner">
          <span className="query-no-docs-icon">📁</span>
          <div>
            <p className="query-no-docs-title">No processed documents yet</p>
            <p className="query-no-docs-hint">
              Upload and process a document first, then come back to ask questions.
            </p>
          </div>
          <button className="query-no-docs-btn" onClick={() => navigate('/')}>
            Upload Documents →
          </button>
        </div>
      )}

      {docsError && (
        <div className="query-error-banner" role="alert">
          <span>⚠️</span>
          <span>Could not load documents. Is the backend running?</span>
        </div>
      )}

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

        {/* Submit row: provider dropdown + submit button */}
        <div className="query-form-footer">
          {/* Provider selector dropdown */}
          <div className="provider-selector">
            <label htmlFor="provider-select" className="provider-label">🤖 Model</label>
            <select
              id="provider-select"
              className="provider-dropdown"
              value={provider}
              onChange={e => setProvider(e.target.value)}
              disabled={loading}
            >
              {PROVIDER_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>
                  {opt.icon} {opt.label}
                </option>
              ))}
            </select>
          </div>

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
              {showDebug ? '🔒 Hide' : '🔓 Show'} debug
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

          {/* Meta row: cache badge + route + latency + reranker count + model badge */}
          <div className="result-meta-row">
            {result.cache_hit && (
              <span className="cache-hit-badge" title="Answer served from Redis cache">
                ⚡ Instant (cached)
              </span>
            )}
            <RouteTag route={result.route_type} />
            {result.model_used && (
              <ModelBadge
                model={result.model_used}
                provider={result.provider_used}
                tokens={result.token_usage?.total_tokens}
                costUsd={result.cost_usd}
              />
            )}
            <span className="result-latency">
              ⏱ {result.latency?.total_ms?.toFixed(0) ?? '—'} ms total
            </span>
            <span className="result-count">
              {result.sources.length} source{result.sources.length !== 1 ? 's' : ''}
            </span>
          </div>

          {/* Answer box */}
          <AnswerBox answer={result.answer} hasModel={!!result.model_used} />

          {/* Performance details panel (Day 7) */}
          <TelemetryPanel latency={result.latency} tokenUsage={result.token_usage} costUsd={result.cost_usd} />

          {/* Debug panel */}
          {showDebug && (
            <DebugPanel
              sources={result.sources}
              route={result.route_type}
              latency={result.latency}
              tokenUsage={result.token_usage}
            />
          )}

          {/* Source cards (citations below answer) */}
          {result.sources.length > 0 && (
            <div className="sources-section">
              <h3 className="sources-heading">
                📎 Sources
                <span className="sources-subhead">grounded citations — sorted by relevance</span>
              </h3>
              <div className="source-cards">
                {result.sources.map((src, idx) => (
                  <SourceCard key={src.chunk_id} source={src} rank={idx + 1} />
                ))}
              </div>
            </div>
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

function ModelBadge({ model, provider, tokens, costUsd }) {
  const providerLabel = provider === 'groq' ? 'Groq' : 'OpenRouter';
  const providerIcon  = provider === 'groq' ? '⚡' : '🔮';
  return (
    <span className="model-badge">
      {providerIcon} <strong>{providerLabel}</strong>
      <span className="model-badge-model">{model}</span>
      {tokens > 0 && <span className="model-badge-tokens">{tokens.toLocaleString()} tokens</span>}
      {costUsd > 0 && <span className="model-badge-cost">${costUsd.toFixed(4)}</span>}
    </span>
  );
}

function AnswerBox({ answer, hasModel }) {
  // Parse [Source X] or 【Source X】 and turn into clickable badges
  const renderAnswerWithCitations = (text) => {
    if (!text) return null;
    
    // Split by [Source X] or 【Source X】
    // The backend uses [Source 1], etc., but some LLMs output full-width brackets.
    const parts = text.split(/([\[【]Source \d+[\]】])/g);
    
    return parts.map((part, i) => {
      const match = part.match(/[\[【]Source (\d+)[\]】]/);
      if (match) {
        const sourceNum = match[1];
        return (
          <a
            key={i}
            href={`#source-card-${sourceNum}`}
            className="citation-badge"
            title={`Go to Source ${sourceNum}`}
            onClick={(e) => {
              e.preventDefault();
              const el = document.getElementById(`source-card-${sourceNum}`);
              if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                el.classList.add('highlight-pulse');
                setTimeout(() => el.classList.remove('highlight-pulse'), 1500);
              }
            }}
          >
            {sourceNum}
          </a>
        );
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div className={`answer-box ${!hasModel ? 'answer-box--placeholder' : ''}`}>
      {!hasModel && (
        <div className="answer-placeholder-badge">
          ⏳ Retrieval only — answer generation coming in next pipeline stage
        </div>
      )}
      <p className="answer-text">{renderAnswerWithCitations(answer)}</p>
    </div>
  );
}

function BBoxGrounding({ bbox, page, chunkType }) {
  if (!bbox || bbox.length !== 4) return null;

  const [x0, y0, x1, y1] = bbox;
  const width  = Math.max(x1 - x0, 0.02);
  const height = Math.max(y1 - y0, 0.02);

  // Color by chunk type
  const colors = {
    text:   { fill: 'rgba(99,102,241,0.25)', stroke: '#6366f1' },
    table:  { fill: 'rgba(16,185,129,0.22)', stroke: '#10b981' },
    figure: { fill: 'rgba(245,158,11,0.22)', stroke: '#f59e0b' },
  };
  const { fill, stroke } = colors[chunkType] || colors.text;

  return (
    <div className="bbox-grounding">
      <div className="bbox-grounding__label">📍 Source location on page {page + 1}</div>
      <div className="bbox-page-thumb" title={`BBox: [${bbox.map(v => v.toFixed(3)).join(', ')}]`}>
        {/* Page background */}
        <svg
          viewBox="0 0 100 141"
          xmlns="http://www.w3.org/2000/svg"
          className="bbox-page-svg"
        >
          {/* Page background */}
          <rect x="0" y="0" width="100" height="141" fill="#1e293b" rx="2" />
          {/* Subtle page lines */}
          {[18, 26, 34, 42, 50, 58, 66, 74, 82, 90, 98, 106, 114, 122].map((y) => (
            <line key={y} x1="8" y1={y} x2="92" y2={y} stroke="#334155" strokeWidth="0.8" />
          ))}
          {/* Highlighted bbox region */}
          <rect
            x={x0 * 100}
            y={y0 * 141}
            width={width * 100}
            height={height * 141}
            fill={fill}
            stroke={stroke}
            strokeWidth="1.5"
            rx="1"
          />
          {/* Corner markers */}
          <rect x={x0 * 100 - 1} y={y0 * 141 - 1} width="3" height="3" fill={stroke} rx="0.5" />
          <rect x={(x0 + width) * 100 - 2} y={y0 * 141 - 1} width="3" height="3" fill={stroke} rx="0.5" />
          <rect x={x0 * 100 - 1} y={(y0 + height) * 141 - 2} width="3" height="3" fill={stroke} rx="0.5" />
          <rect x={(x0 + width) * 100 - 2} y={(y0 + height) * 141 - 2} width="3" height="3" fill={stroke} rx="0.5" />
        </svg>
      </div>
      <div className="bbox-coords">
        [{bbox.map(v => v.toFixed(3)).join(', ')}]
      </div>
    </div>
  );
}

function SourceCard({ source, rank }) {
  const [expanded, setExpanded] = useState(false);
  const typeMeta = CHUNK_TYPE_META[source.chunk_type] || CHUNK_TYPE_META.text;

  return (
    <div className="source-card" id={`source-card-${rank}`}>
      <div className="source-card-header" onClick={() => setExpanded(v => !v)}>
        <span className="source-rank">#{rank}</span>
        {source.filename && (
          <span className="source-filename" title={source.filename}>
            📁 {source.filename}
          </span>
        )}
        <span
          className="source-type-badge"
          style={{ '--badge-color': typeMeta.color }}
        >
          {typeMeta.icon} {typeMeta.label}
        </span>
        <span className="source-page">Page {source.page + 1}</span>
        <span className="source-score">
          {(source.relevance_score * 100).toFixed(1)}%
        </span>
        <span className="source-expand-icon">{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <div className="source-card-body">
          {/* Bbox grounding visual — Day 8 */}
          <BBoxGrounding
            bbox={source.bbox}
            page={source.page}
            chunkType={source.chunk_type}
          />

          <div className="source-preview markdown-body">
            {source.text_preview ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {source.text_preview}
              </ReactMarkdown>
            ) : (
              '(no preview)'
            )}
          </div>
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
                <code>[{source.bbox.map(v => v.toFixed(3)).join(', ')}]</code>
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function TelemetryPanel({ latency, tokenUsage, costUsd }) {
  const [open, setOpen] = useState(false);

  const stages = [
    { label: '🔢 Embedding', ms: latency?.query_embed_ms, color: '#6366f1' },
    { label: '🔍 Retrieval', ms: latency?.retrieval_ms,   color: '#0ea5e9' },
    { label: '🏆 Reranking', ms: latency?.reranking_ms,  color: '#f59e0b' },
    { label: '🤖 LLM',       ms: latency?.llm_ms,         color: '#10b981' },
  ];
  const maxMs = Math.max(...stages.map(s => s.ms || 0), 1);
  const fmtMs = (ms) => {
    if (!ms || ms < 1) return '< 1 ms';
    if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
    return `${ms.toFixed(0)} ms`;
  };

  return (
    <div className="telemetry-panel">
      <button className="telemetry-panel__toggle" onClick={() => setOpen(v => !v)} type="button">
        <span>⚙️ Performance Details</span>
        <span className="telemetry-panel__total">{fmtMs(latency?.total_ms)} total</span>
        <span className="telemetry-panel__chevron">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="telemetry-panel__body">
          <div className="tel-section">
            <h4 className="tel-section-title">⏱ Latency Breakdown</h4>
            {stages.map(({ label, ms, color }) => {
              const pct = Math.min(((ms || 0) / maxMs) * 100, 100);
              return (
                <div key={label} className="tel-bar-row">
                  <span className="tel-bar-label">{label}</span>
                  <div className="tel-bar-track">
                    <div className="tel-bar-fill" style={{ width: `${pct}%`, background: color }} />
                  </div>
                  <span className="tel-bar-value">{fmtMs(ms)}</span>
                </div>
              );
            })}
          </div>
          {tokenUsage && (
            <div className="tel-section">
              <h4 className="tel-section-title">🔤 Token Usage</h4>
              <div className="tel-stats-row">
                <div className="tel-stat">
                  <span className="tel-stat__val">{(tokenUsage.input_tokens || 0).toLocaleString()}</span>
                  <span className="tel-stat__label">Input</span>
                </div>
                <div className="tel-stat">
                  <span className="tel-stat__val">{(tokenUsage.output_tokens || 0).toLocaleString()}</span>
                  <span className="tel-stat__label">Output</span>
                </div>
                <div className="tel-stat tel-stat--accent">
                  <span className="tel-stat__val">{(tokenUsage.total_tokens || 0).toLocaleString()}</span>
                  <span className="tel-stat__label">Total</span>
                </div>
              </div>
            </div>
          )}
          <div className="tel-section">
            <h4 className="tel-section-title">💰 Estimated Cost</h4>
            <div className="tel-cost">
              {costUsd > 0 ? `$${Number(costUsd).toFixed(6)}` : '$0.000000 (free tier)'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DebugPanel({ sources, route, latency, tokenUsage }) {
  return (
    <div className="debug-panel">
      <h4 className="debug-heading">🔬 Pipeline Debug</h4>
      <div className="debug-latency-row">
        <span>Embed: <strong>{latency?.query_embed_ms?.toFixed(0) ?? '—'} ms</strong></span>
        <span>Retrieve: <strong>{latency?.retrieval_ms?.toFixed(0) ?? '—'} ms</strong></span>
        <span>Rerank: <strong>{latency?.reranking_ms?.toFixed(0) ?? '—'} ms</strong></span>
        <span>LLM: <strong>{latency?.llm_ms?.toFixed(0) ?? '—'} ms</strong></span>
        <span>Route: <strong>{route}</strong></span>
      </div>
      {tokenUsage && (
        <div className="debug-latency-row">
          <span>Input tokens: <strong>{tokenUsage.input_tokens ?? 0}</strong></span>
          <span>Output tokens: <strong>{tokenUsage.output_tokens ?? 0}</strong></span>
          <span>Total tokens: <strong>{tokenUsage.total_tokens ?? 0}</strong></span>
        </div>
      )}
      <div className="debug-table-wrapper">
        <table className="debug-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Chunk ID</th>
              <th>File</th>
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
                <td className="debug-preview">{src.filename || '—'}</td>
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
