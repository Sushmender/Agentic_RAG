/**
 * src/pages/QueryPage.jsx
 * Redesigned as a two-pane workspace:
 *   Left: conversation thread + pinned composer
 *   Right: tabbed evidence panel (Sources / Tables / Images / Trace)
 *
 * All original functionality preserved:
 *   - provider selector, doc filter, Ctrl+Enter, citation links,
 *   - BBox grounding, telemetry, debug panel, react-markdown
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Panel, Group, Separator } from 'react-resizable-panels';
import { toast } from 'sonner';
import {
  Send, RotateCcw, Copy, ChevronDown, Zap, Cpu,
  FileText, Table2, Image, Activity, MessageSquare,
  Sparkles, X, Check, AlertTriangle, Info,
} from 'lucide-react';
import { documentsAPI, queryAPI } from '../services/api';
import { Button } from '../components/ui/Button';
import { Tabs } from '../components/ui/Tabs';
import { EmptyState } from '../components/ui/EmptyState';
import { Kbd } from '../components/ui/Kbd';
import { PageEvidence, revokeAllPageBlobUrls } from '../components/PageEvidence';
import { formatRelevance } from '../utils/relevance';
import './QueryPage.css';

function formatModelName(model) {
  if (!model) return '';
  const id = model.split('/').pop() || model;
  if (/qwen/i.test(id)) {
    // Derive version (e.g. 3.8) and size (e.g. 27B) from actual model ID (e.g. qwen3.8-27b)
    const match = id.match(/qwen[^\d]*(\d+(?:\.\d+)?)[^\d]*(\d+b)?/i);
    if (match) {
      const ver = match[1];
      const size = match[2] ? ` ${match[2].toUpperCase()}` : '';
      return `Qwen ${ver}${size}`;
    }
    return 'Qwen 3.8 27B';
  }
  if (/nemotron/i.test(id)) {
    return 'Nemotron 120B';
  }
  return id;
}

/* ── Constants ─────────────────────────────────────────────── */

const PROVIDER_OPTIONS = [
  { value: 'groq',       label: 'Qwen 3.8 27B',   provider: 'Groq',        icon: Zap  },
  { value: 'openrouter', label: 'Nemotron 120B',  provider: 'OpenRouter',  icon: Cpu  },
];

const ROUTE_META = {
  text:       { label: 'Text',       color: 'var(--accent-2)' },
  multimodal: { label: 'Multimodal', color: 'var(--warn)'     },
  hybrid:     { label: 'Hybrid',     color: 'var(--accent)'   },
};

const CHUNK_TYPE_META = {
  text:   { color: 'var(--accent-2)', label: 'Text'   },
  table:  { color: 'var(--accent)',   label: 'Table'  },
  figure: { color: 'var(--warn)',     label: 'Figure' },
};

const SUGGESTED_PROMPTS = [
  'What are the main topics covered?',
  'Summarize the key findings',
  'Show me any tables or charts',
  'What are the conclusions?',
];

/* ── Helper: typewriter reveal ──────────────────────────────── */
function useTypewriter(text, speed = 6) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone]           = useState(false);

  useEffect(() => {
    if (!text) { setDisplayed(''); setDone(false); return; }
    setDisplayed('');
    setDone(false);
    let i = 0;
    const id = setInterval(() => {
      i += speed;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) { setDisplayed(text); setDone(true); clearInterval(id); }
    }, 16);
    return () => clearInterval(id);
  }, [text, speed]);

  const skip = () => { setDisplayed(text); setDone(true); };
  return { displayed, done, skip };
}

/* ── Copy button ────────────────────────────────────────────── */
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button className="copy-btn" onClick={handleCopy} aria-label="Copy answer">
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

/* ── Message bubble ─────────────────────────────────────────── */
function UserBubble({ text }) {
  return (
    <div className="msg msg--user">
      <div className="msg__bubble msg__bubble--user">{text}</div>
    </div>
  );
}

function AssistantBubble({ result, onCitationClick, onRegenerate }) {
  const { displayed, done, skip } = useTypewriter(result.answer);

  const preparedAnswer = useMemo(() => {
    if (!displayed) return '';
    return displayed.replace(/[[【]source\s*(\d+)[\]】]/gi, '[$1](#source-$1)');
  }, [displayed]);

  const routeMeta = ROUTE_META[result.route_type] || ROUTE_META.text;

  return (
    <div className="msg msg--assistant">
      {/* Meta chips */}
      <div className="msg__meta">
        <span className="route-chip" style={{ '--chip-color': routeMeta.color }}>
          {routeMeta.label}
        </span>
        {result.cache_hit && (
          <span className="cache-chip"><Zap size={10} /> Cached</span>
        )}
        {result.latency?.total_ms && (
          <span className="latency-chip">
            {result.latency.total_ms.toFixed(0)} ms
          </span>
        )}
        {result.model_used && (
          <span className="model-chip">
            {formatModelName(result.model_used)}
          </span>
        )}
      </div>

      {/* Answer text */}
      <div
        className={`msg__bubble msg__bubble--assistant ${!done ? 'msg__bubble--typing' : ''}`}
        onClick={() => !done && skip()}
        role={!done ? 'button' : undefined}
        aria-label={!done ? 'Click to skip animation' : undefined}
        aria-live="polite"
      >
        <div className="answer-markdown">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children, ...props }) => {
                if (href?.startsWith('#source-')) {
                  const num = href.replace('#source-', '');
                  return (
                    <a
                      href={href}
                      className="citation-badge"
                      title={`Go to source ${num}`}
                      onClick={(e) => { e.preventDefault(); onCitationClick(num); }}
                      {...props}
                    >
                      {children}
                    </a>
                  );
                }
                return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
              },
            }}
          >
            {preparedAnswer}
          </ReactMarkdown>
        </div>
        {!done && (
          <span className="typing-cursor" aria-hidden="true">|</span>
        )}
      </div>

      {/* Action bar */}
      {done && (
        <div className="msg__actions">
          <CopyButton text={result.answer} />
          <button className="msg-action-btn" onClick={onRegenerate} aria-label="Regenerate answer">
            <RotateCcw size={13} /> Regenerate
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Source card ────────────────────────────────────────────── */
function SourceCard({ source, rank, isHighlighted, allSources = [] }) {
  const [expanded, setExpanded] = useState(false);
  const ext = (source.filename || '').split('.').pop()?.toLowerCase();
  const isImageOrPdf = ['pdf', 'png', 'jpg', 'jpeg', 'webp'].includes(ext);
  const [viewMode, setViewMode] = useState(() => (isImageOrPdf ? 'page' : 'text'));
  const [showDebug, setShowDebug] = useState(false);
  const [fallbackNote, setFallbackNote] = useState(() =>
    !isImageOrPdf ? 'Document format does not support page render — showing extracted text' : ''
  );
  const typeMeta = CHUNK_TYPE_META[source.chunk_type] || CHUNK_TYPE_META.text;

  // Auto-expand and switch to page view when highlighted via citation click (if renderable)
  useEffect(() => {
    if (isHighlighted) {
      setExpanded(true);
      if (isImageOrPdf) {
        setViewMode('page');
      }
    }
  }, [isHighlighted, isImageOrPdf]);

  // All chunks on the same document and page
  const chunksOnPage = useMemo(() => {
    return allSources
      .map((s, idx) => ({ ...s, rank: idx + 1 }))
      .filter((s) => s.document_id === source.document_id && s.page === source.page);
  }, [allSources, source.document_id, source.page]);

  const handlePageError = useCallback(() => {
    setViewMode('text');
    setFallbackNote('Page preview unavailable — showing extracted text');
  }, []);

  return (
    <div
      className={`source-card ${isHighlighted ? 'source-card--highlighted' : ''}`}
      id={`source-${rank}`}
    >
      <button
        className="source-card__header"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
      >
        <span className="source-rank">#{rank}</span>
        <span className="source-type-dot" style={{ background: typeMeta.color }} title={typeMeta.label} />
        <span className="source-filename" title={source.filename}>
          {source.filename || 'Unknown file'}
        </span>
        <span className="source-page">p.{source.page + 1}</span>
        {(() => {
          const rel = formatRelevance(source.relevance_score);
          return (
            <span
              className={`source-score source-score--${rel.tier}`}
              title={`Raw score: ${rel.raw}`}
            >
              {rel.label}
            </span>
          );
        })()}
        <ChevronDown size={14} className={`source-chevron ${expanded ? 'source-chevron--open' : ''}`} />
      </button>

      {expanded && (
        <div className="source-card__body animate-fade-in">
          {/* Text | Page Mode Toggle */}
          <div className="source-card__mode-toggle">
            <div className="source-mode-tabs" role="group" aria-label="Evidence view mode">
              <button
                type="button"
                className={`source-mode-tab ${viewMode === 'page' ? 'source-mode-tab--active' : ''}`}
                onClick={(e) => { e.stopPropagation(); if (isImageOrPdf) setViewMode('page'); }}
                aria-pressed={viewMode === 'page'}
                disabled={!isImageOrPdf}
                title={!isImageOrPdf ? 'Page render unavailable for this document format' : undefined}
              >
                Page
              </button>
              <button
                type="button"
                className={`source-mode-tab ${viewMode === 'text' ? 'source-mode-tab--active' : ''}`}
                onClick={(e) => { e.stopPropagation(); setViewMode('text'); }}
                aria-pressed={viewMode === 'text'}
              >
                Text
              </button>
            </div>
            <span className="source-meta__label">Chunk #{rank}</span>
          </div>

          {/* View mode body */}
          {viewMode === 'page' ? (
            <PageEvidence
              documentId={source.document_id}
              page={source.page}
              activeChunkId={source.chunk_id}
              chunksOnPage={chunksOnPage}
              activeRank={rank}
              isFocused={isHighlighted}
              filename={source.filename}
              onError={handlePageError}
            />
          ) : (
            <div className="source-preview">
              {fallbackNote && (
                <div className="source-fallback-note">
                  <Info size={12} />
                  <span>{fallbackNote}</span>
                </div>
              )}
              {source.text_preview ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{source.text_preview}</ReactMarkdown>
              ) : (
                <p className="text-secondary">No text preview available.</p>
              )}
            </div>
          )}

          {/* Collapsed Debug row */}
          <div className="source-debug-section">
            <button
              type="button"
              className="source-debug-toggle"
              onClick={() => setShowDebug(v => !v)}
              aria-expanded={showDebug}
            >
              <span>Debug metadata</span>
              <ChevronDown size={11} className={showDebug ? 'rotate-180' : ''} />
            </button>
            {showDebug && (
              <div className="source-meta animate-fade-in">
                <span className="source-meta__item">
                  <span className="source-meta__label">Chunk ID</span>
                  <code className="source-meta__val">{source.chunk_id?.slice(0, 16)}…</code>
                </span>
                <span className="source-meta__item">
                  <span className="source-meta__label">Doc ID</span>
                  <code className="source-meta__val">{source.document_id?.slice(0, 12)}…</code>
                </span>
                {source.bbox?.length === 4 && (
                  <span className="source-meta__item">
                    <span className="source-meta__label">BBox [L, T, R, B]</span>
                    <code className="source-meta__val">[{source.bbox.map(v => v.toFixed(3)).join(', ')}]</code>
                  </span>
                )}
                <span className="source-meta__item">
                  <span className="source-meta__label">Raw score</span>
                  <code className="source-meta__val">{Number(source.relevance_score).toFixed(4)}</code>
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Trace panel ────────────────────────────────────────────── */
function TracePanel({ latency, tokenUsage, costUsd }) {
  const stages = [
    { label: 'Embedding',  ms: latency?.query_embed_ms, color: 'var(--color-embed)' },
    { label: 'Retrieval',  ms: latency?.retrieval_ms,   color: 'var(--color-retrieve)' },
    { label: 'Reranking',  ms: latency?.reranking_ms,  color: 'var(--color-rerank)' },
    { label: 'LLM',        ms: latency?.llm_ms,         color: 'var(--color-llm)' },
  ];
  const maxMs = Math.max(...stages.map(s => s.ms || 0), 1);
  const fmt = (ms) => !ms || ms < 1 ? '< 1 ms' : ms >= 1000 ? `${(ms/1000).toFixed(2)} s` : `${ms.toFixed(0)} ms`;

  return (
    <div className="trace-panel">
      <div className="trace-section">
        <h4 className="trace-section__title">Latency Breakdown</h4>
        {stages.map(({ label, ms, color }) => {
          const pct = Math.min(((ms || 0) / maxMs) * 100, 100);
          return (
            <div key={label} className="trace-bar-row">
              <span className="trace-bar-label">{label}</span>
              <div className="trace-bar-track">
                <div className="trace-bar-fill" style={{ width: `${pct}%`, background: color }} />
              </div>
              <span className="trace-bar-val">{fmt(ms)}</span>
            </div>
          );
        })}
        <div className="trace-total">
          Total: <strong>{fmt(latency?.total_ms)}</strong>
        </div>
      </div>
      {tokenUsage && (
        <div className="trace-section">
          <h4 className="trace-section__title">Token Usage</h4>
          <div className="trace-stat-row">
            <div className="trace-stat"><span className="trace-stat__val">{(tokenUsage.input_tokens || 0).toLocaleString()}</span><span className="trace-stat__label">Input</span></div>
            <div className="trace-stat"><span className="trace-stat__val">{(tokenUsage.output_tokens || 0).toLocaleString()}</span><span className="trace-stat__label">Output</span></div>
            <div className="trace-stat trace-stat--accent"><span className="trace-stat__val">{(tokenUsage.total_tokens || 0).toLocaleString()}</span><span className="trace-stat__label">Total</span></div>
          </div>
        </div>
      )}
      <div className="trace-section">
        <h4 className="trace-section__title">Estimated Cost</h4>
        <p className="trace-cost">{costUsd > 0 ? `$${Number(costUsd).toFixed(6)}` : '$0.000000 (free tier)'}</p>
      </div>
    </div>
  );
}

/* ── Query skeleton ─────────────────────────────────────────── */
function QuerySkeleton() {
  return (
    <div className="query-skeleton">
      <div className="skeleton" style={{ height: '24px', width: '40%', marginBottom: '12px', borderRadius: '6px' }} />
      <div className="skeleton" style={{ height: '120px', borderRadius: '10px', marginBottom: '8px' }} />
      <div className="skeleton" style={{ height: '16px', width: '70%', borderRadius: '6px', marginBottom: '4px' }} />
      <div className="skeleton" style={{ height: '16px', width: '50%', borderRadius: '6px' }} />
    </div>
  );
}

/* ── Main page ──────────────────────────────────────────────── */
export default function QueryPage() {
  const location  = useLocation();

  // Conversation history
  const [messages, setMessages] = useState([]); // {type:'user'|'assistant', content, result?}
  const [query, setQuery]       = useState('');
  const [provider, setProvider] = useState('groq');
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState(null);

  // Documents
  const [documents, setDocuments]       = useState([]);
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [docsLoading, setDocsLoading]   = useState(true);

  // Evidence pane
  const [evidenceTab, setEvidenceTab]   = useState('sources');
  const [highlighted, setHighlighted]   = useState(null);

  const textareaRef  = useRef(null);
  const bottomRef    = useRef(null);

  // Get pre-selected doc from query string
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const docId  = params.get('doc');
    if (docId) setSelectedDocs([docId]);
  }, [location.search]);

  // Load documents
  useEffect(() => {
    setDocsLoading(true);
    documentsAPI.list()
      .then(res => {
        const completed = (res.data.documents || []).filter(d => d.status === 'completed');
        setDocuments(completed);
      })
      .catch(() => toast.error('Could not load documents.'))
      .finally(() => setDocsLoading(false));
  }, []);

  // Auto-scroll to bottom on new message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Cleanup page blob URLs on unmount
  useEffect(() => {
    return () => {
      revokeAllPageBlobUrls();
    };
  }, []);

  // Auto-resize textarea
  const handleQueryChange = (e) => {
    setQuery(e.target.value);
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
    }
  };

  const toggleDoc = useCallback((docId) => {
    setSelectedDocs(prev =>
      prev.includes(docId) ? prev.filter(id => id !== docId) : [...prev, docId]
    );
  }, []);

  // Latest result (from last assistant message)
  const lastResult = useMemo(() => {
    const assistantMsgs = messages.filter(m => m.type === 'assistant');
    return assistantMsgs.length > 0 ? assistantMsgs[assistantMsgs.length - 1].result : null;
  }, [messages]);

  const sourcesForCurrentResult = lastResult?.sources || [];
  const tablesInSources  = sourcesForCurrentResult.filter(s => s.chunk_type === 'table');
  const imagesInSources  = sourcesForCurrentResult.filter(s => s.chunk_type === 'figure');

  /* Submit */
  const handleSubmit = async (e) => {
    e?.preventDefault();
    const q = query.trim();
    if (!q || loading) return;

    setMessages(prev => [...prev, { type: 'user', content: q }]);
    setQuery('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    setLoading(true);
    setError(null);

    try {
      const res = await queryAPI.query({
        query:        q,
        document_ids: selectedDocs.length > 0 ? selectedDocs : null,
        llm_provider: provider,
      });
      setMessages(prev => [...prev, { type: 'assistant', content: res.data.answer, result: res.data }]);
      setEvidenceTab('sources');
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail || err.message || 'Query failed.';
      let msg = detail;
      if (status === 429) msg = 'Rate limit reached — wait a moment and try again.';
      else if (status >= 500) msg = `Server error: ${detail}`;
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleSubmit(e);
  };

  const handleCitationClick = (num) => {
    setEvidenceTab('sources');
    setHighlighted(num);
    setTimeout(() => {
      const el = document.getElementById(`source-${num}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('source-card--highlighted');
        setTimeout(() => {
          el.classList.remove('source-card--highlighted');
          setHighlighted(null);
        }, 1600);
      }
    }, 100);
  };

  const handleRegenerate = () => {
    const lastUser = [...messages].reverse().find(m => m.type === 'user');
    if (lastUser) {
      setMessages(prev => prev.slice(0, -1)); // remove last assistant msg
      setQuery(lastUser.content);
    }
  };

  const clearConversation = () => {
    setMessages([]);
    setError(null);
  };

  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' && window.innerWidth <= 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const evidenceTabs = [
    { value: 'sources', label: 'Sources',   count: sourcesForCurrentResult.length },
    { value: 'tables',  label: 'Tables',    count: tablesInSources.length },
    { value: 'images',  label: 'Images',    count: imagesInSources.length },
    { value: 'trace',   label: 'Trace' },
  ];

  return (
    <div className="query-page">
      <Group orientation={isMobile ? 'vertical' : 'horizontal'} className="query-panels">
        {/* ── Left: Conversation ──────────────────────────────── */}
        <Panel defaultSize="60%" minSize="35%" className="conv-panel">
          <div className="conv-panel__inner">
            {/* Conversation thread */}
            <div className="conv-thread" aria-live="polite" aria-label="Conversation">
              {messages.length === 0 && !loading && (
                <div className="conv-empty">
                  <EmptyState
                    icon={<MessageSquare size={24} />}
                    title="Ask anything"
                    description="Query your documents using multimodal RAG — text, tables, figures, and images."
                  />
                  <div className="suggested-prompts">
                    {SUGGESTED_PROMPTS.map(p => (
                      <button key={p} className="suggested-prompt" onClick={() => { setQuery(p); textareaRef.current?.focus(); }}>
                        <Sparkles size={12} />
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg, i) => {
                if (msg.type === 'user') return <UserBubble key={i} text={msg.content} />;
                return (
                  <AssistantBubble
                    key={i}
                    result={msg.result}
                    onCitationClick={handleCitationClick}
                    onRegenerate={i === messages.length - 1 ? handleRegenerate : undefined}
                  />
                );
              })}

              {loading && <QuerySkeleton />}

              {error && (
                <div className="conv-error" role="alert">
                  <AlertTriangle size={15} />
                  {error}
                </div>
              )}

              <div ref={bottomRef} />
            </div>

            {/* Pinned composer */}
            <div className="composer">
              {/* Doc filter chips */}
              {!docsLoading && documents.length > 0 && (
                <div className="composer__doc-chips">
                  {selectedDocs.map(id => {
                    const doc = documents.find(d => d.document_id === id);
                    if (!doc) return null;
                    return (
                      <span key={id} className="doc-filter-chip">
                        {doc.filename}
                        <button
                          className="doc-filter-chip__remove"
                          onClick={() => toggleDoc(id)}
                          aria-label={`Remove ${doc.filename} filter`}
                        >
                          <X size={10} />
                        </button>
                      </span>
                    );
                  })}
                  {selectedDocs.length === 0 && (
                    <span className="composer__doc-hint">All documents · </span>
                  )}
                  <div className="doc-filter-dropdown">
                    <button className="doc-filter-dropdown__btn" aria-label="Select documents to filter">
                      Filter docs <ChevronDown size={11} />
                    </button>
                    <div className="doc-filter-dropdown__menu">
                      {documents.map(doc => (
                        <label key={doc.document_id} className="doc-filter-option">
                          <input
                            type="checkbox"
                            checked={selectedDocs.includes(doc.document_id)}
                            onChange={() => toggleDoc(doc.document_id)}
                          />
                          {doc.filename}
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              <form className="composer__form" onSubmit={handleSubmit}>
                <div className="composer__textarea-wrap">
                  <textarea
                    ref={textareaRef}
                    id="query-input"
                    className="composer__textarea"
                    placeholder="Ask anything about your documents…"
                    value={query}
                    onChange={handleQueryChange}
                    onKeyDown={handleKeyDown}
                    rows={1}
                    disabled={loading}
                    aria-label="Query input"
                  />
                </div>
                <div className="composer__footer">
                  <div className="composer__footer-left">
                    <select
                      className="model-select"
                      value={provider}
                      onChange={e => setProvider(e.target.value)}
                      disabled={loading}
                      aria-label="Select model"
                    >
                      {PROVIDER_OPTIONS.map(o => (
                        <option key={o.value} value={o.value}>{o.provider} — {o.label}</option>
                      ))}
                    </select>
                    {messages.length > 0 && (
                      <button type="button" className="clear-btn" onClick={clearConversation} aria-label="Clear conversation">
                        Clear
                      </button>
                    )}
                  </div>
                  <div className="composer__footer-right">
                    <span className="composer__hint"><Kbd>Ctrl</Kbd>+<Kbd>Enter</Kbd></span>
                    <Button
                      id="query-submit-btn"
                      type="submit"
                      variant="primary"
                      size="md"
                      loading={loading}
                      disabled={!query.trim() || loading}
                      icon={<Send size={14} />}
                    >
                      Ask
                    </Button>
                  </div>
                </div>
              </form>
            </div>
          </div>
        </Panel>

        <Separator className="panel-resize-handle" />

        {/* ── Right: Evidence ─────────────────────────────────── */}
        <Panel defaultSize="40%" minSize="25%" className="evidence-panel">
          <div className="evidence-panel__inner">
            <div className="evidence-panel__header">
              <Tabs
                tabs={evidenceTabs}
                active={evidenceTab}
                onChange={setEvidenceTab}
              />
            </div>

            <div className="evidence-panel__body">
              {/* No result yet */}
              {!lastResult && !loading && (
                <EmptyState
                  icon={<Activity size={22} />}
                  title="Evidence panel"
                  description="Sources, tables, images, and trace will appear here after you ask a question."
                />
              )}

              {/* Sources tab */}
              {lastResult && evidenceTab === 'sources' && (
                <div className="sources-list">
                  {sourcesForCurrentResult.length === 0 ? (
                    <EmptyState icon={<FileText size={20} />} title="No sources" description="No matching chunks were found for this query." />
                  ) : (
                    sourcesForCurrentResult.map((src, i) => (
                      <SourceCard
                        key={src.chunk_id}
                        source={src}
                        rank={i + 1}
                        isHighlighted={highlighted === String(i + 1)}
                        allSources={sourcesForCurrentResult}
                      />
                    ))
                  )}
                </div>
              )}

              {/* Tables tab */}
              {lastResult && evidenceTab === 'tables' && (
                <div className="tables-list">
                  {tablesInSources.length === 0 ? (
                    <EmptyState icon={<Table2 size={20} />} title="No tables" description="No table chunks were retrieved for this query." />
                  ) : (
                    tablesInSources.map(src => (
                      <div key={src.chunk_id} className="table-chunk">
                        <div className="table-chunk__header">
                          <span>Table from {src.filename} · p.{src.page + 1}</span>
                          {(() => {
                            const rel = formatRelevance(src.relevance_score);
                            return (
                              <span
                                className={`source-score source-score--${rel.tier}`}
                                title={`Raw score: ${rel.raw}`}
                              >
                                {rel.label}
                              </span>
                            );
                          })()}
                        </div>
                        <div className="table-chunk__content">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{src.text_preview}</ReactMarkdown>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Images tab */}
              {lastResult && evidenceTab === 'images' && (
                <div className="images-list">
                  {imagesInSources.length === 0 ? (
                    <EmptyState icon={<Image size={20} />} title="No images" description="No figure chunks were retrieved for this query." />
                  ) : (
                    imagesInSources.map(src => (
                      <div key={src.chunk_id} className="image-chunk">
                        <div className="image-chunk__header">
                          Figure from {src.filename} · p.{src.page + 1}
                        </div>
                        <div className="image-chunk__content">
                          {src.text_preview && (
                            <p className="image-chunk__caption">{src.text_preview.slice(0, 200)}</p>
                          )}
                          {src.bbox?.length === 4 && (
                            <div className="bbox-mini">
                              <svg viewBox="0 0 100 141" className="bbox-mini__svg">
                                <rect x="0" y="0" width="100" height="141" fill="var(--bg-elevated)" rx="2" />
                                {[18,26,34,42,50,58,66,74,82,90,98,106,114,122].map(y => (
                                  <line key={y} x1="8" y1={y} x2="92" y2={y} stroke="var(--border)" strokeWidth="0.8" />
                                ))}
                                <rect
                                  x={src.bbox[0]*100} y={src.bbox[1]*141}
                                  width={Math.max(src.bbox[2]-src.bbox[0],0.02)*100}
                                  height={Math.max(src.bbox[3]-src.bbox[1],0.02)*141}
                                  fill="rgba(255,181,71,0.2)" stroke="var(--warn)" strokeWidth="1.5" rx="1"
                                />
                              </svg>
                              <span className="bbox-mini__label">Page {src.page + 1}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Trace tab */}
              {lastResult && evidenceTab === 'trace' && (
                <TracePanel
                  latency={lastResult.latency}
                  tokenUsage={lastResult.token_usage}
                  costUsd={lastResult.cost_usd}
                />
              )}
            </div>
          </div>
        </Panel>
      </Group>
    </div>
  );
}
