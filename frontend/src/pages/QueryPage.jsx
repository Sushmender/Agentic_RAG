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

import { useCallback, useEffect, useMemo, useRef, useState, Component } from 'react';
import { useLocation } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Panel, Group, Separator } from 'react-resizable-panels';
import { toast } from 'sonner';
import {
  Send, RotateCcw, Copy, ChevronDown, Zap, Cpu,
  FileText, Table2, Image, Activity, MessageSquare,
  Sparkles, X, Check, AlertTriangle, Info, Highlighter, Quote,
} from 'lucide-react';
import { documentsAPI } from '../services/api';
import { Button } from '../components/ui/Button';
import { Tabs } from '../components/ui/Tabs';
import { EmptyState } from '../components/ui/EmptyState';
import { Kbd } from '../components/ui/Kbd';
import { Tooltip } from '../components/ui/Tooltip';
import { PageEvidence, revokeAllPageBlobUrls } from '../components/PageEvidence';
import { formatRelevance } from '../utils/relevance';
import { findSupportingSentences, highlightInChildren } from '../utils/highlight';
import { useChat, createDefaultTab } from '../context/ChatContext';
import { ChatTabStrip } from '../components/chat/ChatTabStrip';
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

function AssistantBubble({
  msg,
  isActiveEvidence,
  onSelectEvidence,
  onCitationClick,
  onRegenerate,
  onRevealed,
}) {
  const result = msg.result;
  const isAlreadyRevealed = msg.revealed === true;
  const { displayed, done, skip } = useTypewriter(
    isAlreadyRevealed ? '' : (result?.answer || ''),
    6
  );

  useEffect(() => {
    if (!isAlreadyRevealed && done) {
      onRevealed?.();
    }
  }, [isAlreadyRevealed, done, onRevealed]);

  const handleSkip = (e) => {
    e?.stopPropagation();
    skip();
    onRevealed?.();
  };

  const finalDisplayed = isAlreadyRevealed ? (result?.answer || '') : displayed;
  const isTyping = !isAlreadyRevealed && !done;

  const preparedAnswer = useMemo(() => {
    if (!finalDisplayed) return '';
    return finalDisplayed.replace(/[[【]source\s*(\d+)[\]】]/gi, '[$1](#source-$1)');
  }, [finalDisplayed]);

  if (msg.error) {
    return (
      <div className="msg msg--assistant">
        <div className="conv-error" role="alert">
          <AlertTriangle size={15} />
          <span>{msg.error}</span>
          {onRegenerate && (
            <button
              type="button"
              className="msg-action-btn"
              onClick={onRegenerate}
              style={{ marginLeft: 'auto' }}
              aria-label="Regenerate interrupted query"
            >
              <RotateCcw size={13} /> Regenerate
            </button>
          )}
        </div>
      </div>
    );
  }

  if (msg.pending || !result) {
    return <QuerySkeleton />;
  }

  const routeMeta = ROUTE_META[result.route_type] || ROUTE_META.text;

  return (
    <div
      className={`msg msg--assistant ${isActiveEvidence ? 'msg--active-evidence' : ''}`}
      onClick={onSelectEvidence}
    >
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
        {isActiveEvidence && (
          <span className="evidence-active-badge" title="Evidence for this answer is shown on the right">
            Viewing evidence
          </span>
        )}
      </div>

      {/* Answer text */}
      <div
        className={`msg__bubble msg__bubble--assistant ${isTyping ? 'msg__bubble--typing' : ''}`}
        onClick={isTyping ? handleSkip : undefined}
        role={isTyping ? 'button' : undefined}
        aria-label={isTyping ? 'Click to skip animation' : undefined}
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
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        onCitationClick(num);
                      }}
                      {...props}
                    >
                      {children}
                    </a>
                  );
                }
                return (
                  <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                    {children}
                  </a>
                );
              },
            }}
          >
            {preparedAnswer}
          </ReactMarkdown>
        </div>
        {isTyping && (
          <span className="typing-cursor" aria-hidden="true">|</span>
        )}
      </div>

      {/* Action bar */}
      {!isTyping && (
        <div className="msg__actions">
          <CopyButton text={result.answer} />
          {onRegenerate && (
            <button
              type="button"
              className="msg-action-btn"
              onClick={(e) => {
                e.stopPropagation();
                onRegenerate();
              }}
              aria-label="Regenerate answer"
            >
              <RotateCcw size={13} /> Regenerate
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Source card ────────────────────────────────────────────── */
function SourceCard({ source, rank, isHighlighted, allSources = [], answer = '', query = '' }) {
  const [expanded, setExpanded] = useState(false);
  const ext = (source.filename || '').split('.').pop()?.toLowerCase();
  const isImageOrPdf = ['pdf', 'png', 'jpg', 'jpeg', 'webp', 'tiff'].includes(ext);
  const [viewMode, setViewMode] = useState(() => (isImageOrPdf ? 'page' : 'text'));
  const [showDebug, setShowDebug] = useState(false);
  const [fallbackNote, setFallbackNote] = useState('');
  const [expandedText, setExpandedText] = useState(false);
  const [isClamped, setIsClamped] = useState(false);
  const contentRef = useRef(null);

  // Persistent highlight on/off toggle
  const [highlightEnabled, setHighlightEnabled] = useState(() => {
    try {
      const saved = localStorage.getItem('rag_source_highlight');
      return saved !== null ? JSON.parse(saved) : true;
    } catch {
      return true;
    }
  });

  const toggleHighlight = (e) => {
    e?.stopPropagation();
    setHighlightEnabled((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('rag_source_highlight', JSON.stringify(next));
      } catch {}
      return next;
    });
  };

  const typeMeta = CHUNK_TYPE_META[source.chunk_type] || CHUNK_TYPE_META.text;

  // Extract leading markdown heading and clean body
  const { extractedHeading, cleanBody } = useMemo(() => {
    const raw = source.text_preview || '';
    const stripped = raw.replace(/^<a\s+id=['"][^'"]*['"]>\s*<\/a>\s*/i, '').trimStart();
    const headingMatch = stripped.match(/^(#{1,6})\s+([^\n]+)(?:\n+([\s\S]*))?$/);
    if (headingMatch) {
      const h = headingMatch[2].trim();
      const b = (headingMatch[3] || '').trim();
      return {
        extractedHeading: h,
        cleanBody: b || stripped,
      };
    }
    return { extractedHeading: null, cleanBody: stripped };
  }, [source.text_preview]);

  // Section context line: breadcrumb > section/heading > extracted heading
  const sectionContext = useMemo(() => {
    if (source.breadcrumb) return source.breadcrumb;
    if (source.section && source.heading && source.section !== source.heading) {
      return `${source.section} › ${source.heading}`;
    }
    if (source.section) return source.section;
    if (source.heading) return source.heading;
    if (extractedHeading) return extractedHeading;
    return null;
  }, [source.breadcrumb, source.section, source.heading, extractedHeading]);

  // Header location badge:
  // PPTX -> Slide N; XLSX -> Sheet name; DOCX -> Section heading if available, otherwise hide; PDF/image -> p.N
  const locationBadge = useMemo(() => {
    if (isImageOrPdf) {
      return source.page !== undefined && source.page !== null ? `p.${source.page + 1}` : null;
    }
    if (ext === 'pptx' || ext === 'ppt') {
      if (source.slide) return `Slide ${source.slide}`;
      if (source.page !== undefined && source.page !== null) return `Slide ${source.page + 1}`;
      return null;
    }
    if (ext === 'xlsx' || ext === 'xls' || ext === 'csv') {
      if (source.sheet_name) return source.sheet_name;
      if (source.sheet) return source.sheet;
      return null;
    }
    if (ext === 'docx' || ext === 'doc') {
      if (source.section) return source.section;
      if (source.heading) return source.heading;
      if (extractedHeading) return extractedHeading;
      return null;
    }
    if (source.section) return source.section;
    if (source.heading) return source.heading;
    if (extractedHeading) return extractedHeading;
    return null;
  }, [isImageOrPdf, ext, source.page, source.slide, source.sheet_name, source.sheet, source.section, source.heading, extractedHeading]);

  // Supporting sentences for highlight
  const supportingSentences = useMemo(() => {
    if (!highlightEnabled || !answer) return [];
    return findSupportingSentences(cleanBody, answer, query);
  }, [highlightEnabled, cleanBody, answer, query]);

  // Auto-expand and switch to page view when highlighted via citation click (if renderable)
  useEffect(() => {
    if (isHighlighted) {
      setExpanded(true);
      if (isImageOrPdf) {
        setViewMode('page');
      }
    }
  }, [isHighlighted, isImageOrPdf]);

  // Check if content exceeds ~6 lines to show "Show more" toggle
  useEffect(() => {
    if (contentRef.current) {
      const raf = requestAnimationFrame(() => {
        if (contentRef.current) {
          setIsClamped(contentRef.current.scrollHeight > 155);
        }
      });
      return () => cancelAnimationFrame(raf);
    }
  }, [cleanBody, expanded, viewMode]);

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

  // Citation string: filename — section/slide/sheet
  const getCitationString = () => {
    const filename = source.filename || 'Unknown file';
    let target = '';
    if (isImageOrPdf) {
      target = source.page !== undefined ? `p.${source.page + 1}` : '';
    } else if (ext === 'pptx' || ext === 'ppt') {
      target = source.slide ? `Slide ${source.slide}` : (source.page !== undefined ? `Slide ${source.page + 1}` : '');
    } else if (ext === 'xlsx' || ext === 'xls' || ext === 'csv') {
      target = source.sheet_name || source.sheet || (source.page !== undefined ? `Sheet ${source.page + 1}` : '');
    } else if (ext === 'docx' || ext === 'doc') {
      target = source.section || source.heading || sectionContext || '';
    } else {
      target = sectionContext || (source.page !== undefined ? `p.${source.page + 1}` : '');
    }

    return target ? `${filename} — ${target}` : filename;
  };

  const handleCopyCitation = async (e) => {
    e.stopPropagation();
    const citation = getCitationString();
    try {
      await navigator.clipboard.writeText(citation);
      toast.success('Citation copied');
    } catch {
      toast.error('Failed to copy citation');
    }
  };

  const handleCopyText = async (e) => {
    e.stopPropagation();
    const textToCopy = cleanBody || source.text_preview || '';
    try {
      await navigator.clipboard.writeText(textToCopy);
      toast.success('Text copied');
    } catch {
      toast.error('Failed to copy text');
    }
  };

  // Markdown custom renderers for tables, paragraphs with highlighted sentences
  const markdownComponents = useMemo(() => ({
    table: ({ children, ...props }) => (
      <div className="source-table-wrapper">
        <table className="source-table" {...props}>
          {children}
        </table>
      </div>
    ),
    p: ({ children, ...props }) => (
      <p {...props}>{highlightInChildren(children, supportingSentences)}</p>
    ),
    li: ({ children, ...props }) => (
      <li {...props}>{highlightInChildren(children, supportingSentences)}</li>
    ),
    td: ({ children, ...props }) => (
      <td {...props}>{highlightInChildren(children, supportingSentences)}</td>
    ),
    blockquote: ({ children, ...props }) => (
      <blockquote {...props}>{highlightInChildren(children, supportingSentences)}</blockquote>
    ),
  }), [supportingSentences]);

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
        {locationBadge && (
          <span className="source-page" title={locationBadge}>
            {locationBadge}
          </span>
        )}
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
          {/* Mode Toggle or Non-renderable format chip */}
          <div className="source-card__mode-toggle">
            {isImageOrPdf ? (
              <div className="source-mode-tabs" role="group" aria-label="Evidence view mode">
                <button
                  type="button"
                  className={`source-mode-tab ${viewMode === 'page' ? 'source-mode-tab--active' : ''}`}
                  onClick={(e) => { e.stopPropagation(); setViewMode('page'); }}
                  aria-pressed={viewMode === 'page'}
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
            ) : (
              <Tooltip content="Page preview is available for PDFs and images" placement="top">
                <span className="source-format-chip">
                  <FileText size={12} className="source-format-icon" />
                  <span>{(ext || 'txt').toUpperCase()} · text view</span>
                </span>
              </Tooltip>
            )}
            <span className="source-meta__label">Chunk #{rank}</span>
          </div>

          {/* View mode body */}
          {isImageOrPdf && viewMode === 'page' ? (
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

              {/* Section Context line */}
              {sectionContext && (
                <div className="source-section-context" title={sectionContext}>
                  <FileText size={11} className="source-section-icon" />
                  <span className="source-section-text">{sectionContext}</span>
                </div>
              )}

              {/* Clamped markdown body */}
              <div
                ref={contentRef}
                className={`source-preview-content ${
                  isClamped && !expandedText ? 'source-preview-content--clamped' : ''
                }`}
              >
                {cleanBody ? (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={markdownComponents}
                  >
                    {cleanBody}
                  </ReactMarkdown>
                ) : (
                  <p className="text-secondary">No text preview available.</p>
                )}
              </div>

              {isClamped && (
                <button
                  type="button"
                  className="source-expand-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setExpandedText((v) => !v);
                  }}
                  aria-expanded={expandedText}
                >
                  {expandedText ? 'Show less' : 'Show more'}
                </button>
              )}
            </div>
          )}

          {/* Action Row */}
          <div className="source-card__actions">
            <button
              type="button"
              className="source-action-btn"
              onClick={handleCopyText}
              title="Copy chunk text"
            >
              <Copy size={12} />
              <span>Copy text</span>
            </button>
            <button
              type="button"
              className="source-action-btn"
              onClick={handleCopyCitation}
              title="Copy citation"
            >
              <Quote size={12} />
              <span>Copy citation</span>
            </button>
            <button
              type="button"
              className={`source-action-btn source-action-btn--toggle ${
                highlightEnabled ? 'source-action-btn--active' : ''
              }`}
              onClick={toggleHighlight}
              title={
                highlightEnabled
                  ? 'Highlight: on (click to disable)'
                  : 'Highlight: off (click to enable)'
              }
              aria-pressed={highlightEnabled}
            >
              <Highlighter size={12} />
              <span>Highlight: {highlightEnabled ? 'on' : 'off'}</span>
            </button>
          </div>

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
function TracePanel({ latency, tokenUsage, costUsd, embedAttempts, embedCacheHit }) {
  const stages = [
    {
      label: 'Embedding',
      ms: latency?.query_embed_ms,
      color: 'var(--color-embed)',
      attempts: embedAttempts,
      cached: embedCacheHit,
    },
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
        {stages.map(({ label, ms, color, attempts, cached }) => {
          const pct = Math.min(((ms || 0) / maxMs) * 100, 100);
          return (
            <div key={label} className="trace-bar-row">
              <span className="trace-bar-label" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                {label}
                {attempts != null && attempts > 1 && (
                  <span
                    className="trace-attempt-badge"
                    style={{
                      fontSize: '10px',
                      padding: '1px 5px',
                      borderRadius: '4px',
                      background: 'rgba(234, 179, 8, 0.15)',
                      color: 'var(--warn, #eab308)',
                      border: '1px solid rgba(234, 179, 8, 0.3)',
                    }}
                  >
                    {attempts} attempts
                  </span>
                )}
                {cached === true && (
                  <span
                    className="trace-cached-chip"
                    style={{
                      fontSize: '10px',
                      padding: '1px 5px',
                      borderRadius: '4px',
                      background: 'rgba(45, 226, 166, 0.12)',
                      color: 'var(--accent, #2de2a6)',
                      border: '1px solid rgba(45, 226, 166, 0.25)',
                    }}
                  >
                    cached
                  </span>
                )}
              </span>
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
  const [takingLonger, setTakingLonger] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setTakingLonger(true);
    }, 8000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="query-skeleton">
      <div className="skeleton" style={{ height: '24px', width: '40%', marginBottom: '12px', borderRadius: '6px' }} />
      <div className="skeleton" style={{ height: '120px', borderRadius: '10px', marginBottom: '8px' }} />
      <div className="skeleton" style={{ height: '16px', width: '70%', borderRadius: '6px', marginBottom: '4px' }} />
      <div className="skeleton" style={{ height: '16px', width: '50%', borderRadius: '6px' }} />
      {takingLonger && (
        <div
          className="query-skeleton__longer"
          style={{
            fontSize: '12px',
            color: 'var(--text-muted, #8a94ad)',
            marginTop: '8px',
            fontStyle: 'italic',
          }}
        >
          Taking longer than usual…
        </div>
      )}
    </div>
  );
}

/* ── Panel Layout Validation & Error Boundary ───────────────── */
const PANEL_STORAGE_KEY = 'react-resizable-panels:rag-query-panels';

function getValidatedPanelLayout() {
  try {
    for (const key of [PANEL_STORAGE_KEY, 'rag-query-panels']) {
      const raw = localStorage.getItem(key);
      if (!raw) continue;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length >= 2) {
        const left = Number(parsed[0]);
        const right = Number(parsed[1]);
        if (left >= 30 && right >= 20 && !Number.isNaN(left) && !Number.isNaN(right)) {
          return { 'conv-panel': left, 'evidence-panel': right };
        }
      } else if (parsed && typeof parsed === 'object') {
        const values = Object.values(parsed).map(Number);
        if (values.length >= 2) {
          const [left, right] = values;
          if (left >= 30 && right >= 20 && !Number.isNaN(left) && !Number.isNaN(right)) {
            return parsed;
          }
        }
      }
      // Stored layout is 0, below minimum, or corrupted -> ignore and remove
      localStorage.removeItem(key);
    }
  } catch {
    try {
      localStorage.removeItem(PANEL_STORAGE_KEY);
      localStorage.removeItem('rag-query-panels');
    } catch {}
  }
  return null;
}

class QueryErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('QueryErrorBoundary caught:', error, info);
  }

  handleResetView = () => {
    try {
      localStorage.removeItem(PANEL_STORAGE_KEY);
      localStorage.removeItem('rag-query-panels');
    } catch {}
    this.props.onResetView?.();
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="query-view-fallback" style={{ display: 'flex', minHeight: '320px', width: '100%' }}>
          <div className="query-view-fallback__card">
            <div className="query-view-fallback__icon">
              <AlertTriangle size={30} />
            </div>
            <h2>Unable to display query workspace</h2>
            <p>
              An unexpected display issue occurred in this view. Your conversations and messages are safe.
            </p>
            <Button
              variant="primary"
              onClick={this.handleResetView}
              icon={<RotateCcw size={14} />}
            >
              Reset this view
            </Button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

/* ── Main query workspace inner component ───────────────────── */
function QueryPageInner() {
  const location = useLocation();

  const {
    activeTab: contextActiveTab,
    tabs,
    activeTabId,
    setActive,
    updateTab,
    sendMessage,
    clearTab,
    markMessageRevealed,
  } = useChat();

  // Safeguard: QueryPage must never render nothing. Fall back to default tab if missing.
  const activeTab = useMemo(() => {
    if (contextActiveTab && contextActiveTab.id) return contextActiveTab;
    const found = tabs.find((t) => t.id === activeTabId);
    if (found) return found;
    const defaultTab = tabs.find((t) => t.id === 'default');
    if (defaultTab) return defaultTab;
    return tabs[0] || createDefaultTab();
  }, [contextActiveTab, tabs, activeTabId]);

  // Correct activeTabId in the store if pointing to missing tab
  useEffect(() => {
    if (!tabs.some((t) => t.id === activeTabId)) {
      setActive('default');
    }
  }, [tabs, activeTabId, setActive]);

  const messages = useMemo(() => activeTab.messages || [], [activeTab.messages]);
  const query = activeTab.draft || '';
  const provider = activeTab.model || 'groq';
  const selectedDocs = activeTab.docIds || [];
  const evidenceTab = activeTab.evidenceTab || 'sources';

  // In-flight query in this tab
  const isTabLoading = messages.some((m) => m.pending);

  // Documents
  const [documents, setDocuments] = useState([]);
  const [docsLoading, setDocsLoading] = useState(true);

  // Evidence pane
  const [highlighted, setHighlighted] = useState(null);

  const textareaRef = useRef(null);
  const bottomRef = useRef(null);
  const activeTabRef = useRef(activeTab);

  useEffect(() => {
    activeTabRef.current = activeTab;
  }, [activeTab]);

  // Handle URL pre-selected doc param
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const docId = params.get('doc');
    if (docId && activeTab) {
      if (!activeTab.docIds?.includes(docId)) {
        updateTab(activeTab.id, { docIds: [docId] });
      }
    }
  }, [location.search, activeTab, updateTab]);

  // Load documents
  const loadDocuments = useCallback(async () => {
    setDocsLoading(true);
    try {
      const res = await documentsAPI.list();
      const completed = (res.data.documents || []).filter((d) => d.status === 'completed');
      setDocuments(completed);

      // Check if any filtered document was deleted
      const currentTab = activeTabRef.current;
      if (currentTab && currentTab.docIds && currentTab.docIds.length > 0) {
        const validDocs = currentTab.docIds.filter((id) =>
          completed.some((d) => d.document_id === id)
        );
        if (validDocs.length < currentTab.docIds.length) {
          updateTab(currentTab.id, {
            docIds: validDocs,
            docNotice: 'A filtered document was deleted and removed from this chat.',
          });
        }
      }
    } catch {
      toast.error('Could not load documents.');
    } finally {
      setDocsLoading(false);
    }
  }, [updateTab]);

  useEffect(() => {
    loadDocuments();
    window.addEventListener('focus', loadDocuments);
    return () => window.removeEventListener('focus', loadDocuments);
  }, [loadDocuments]);

  // Auto-scroll to bottom on new message or loading
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTabLoading]);

  // Cleanup page blob URLs on unmount
  useEffect(() => {
    return () => {
      revokeAllPageBlobUrls();
    };
  }, []);

  // Auto-resize textarea
  const handleQueryChange = (e) => {
    updateTab(activeTab.id, { draft: e.target.value });
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
    }
  };

  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
    }
  }, [activeTab.draft]);

  const toggleDoc = useCallback(
    (docId) => {
      const current = activeTab.docIds || [];
      const updated = current.includes(docId)
        ? current.filter((id) => id !== docId)
        : [...current, docId];
      updateTab(activeTab.id, { docIds: updated });
    },
    [activeTab.id, activeTab.docIds, updateTab]
  );

  // Active result for evidence panel
  const activeResultMsg = useMemo(() => {
    const msgs = activeTab.messages || [];
    if (activeTab.activeMessageId) {
      const found = msgs.find((m) => m.id === activeTab.activeMessageId && m.result);
      if (found) return found;
    }
    const assistantMsgs = msgs.filter((m) => m.type === 'assistant' && m.result);
    return assistantMsgs.length > 0 ? assistantMsgs[assistantMsgs.length - 1] : null;
  }, [activeTab.messages, activeTab.activeMessageId]);

  const lastResult = activeResultMsg?.result || null;
  const sourcesForCurrentResult = useMemo(() => lastResult?.sources || [], [lastResult?.sources]);
  const tablesInSources = useMemo(() => sourcesForCurrentResult.filter((s) => s.chunk_type === 'table'), [sourcesForCurrentResult]);
  const imagesInSources = useMemo(() => sourcesForCurrentResult.filter((s) => s.chunk_type === 'figure'), [sourcesForCurrentResult]);

  const [showLowRelevance, setShowLowRelevance] = useState(false);

  useEffect(() => {
    setShowLowRelevance(false);
  }, [activeResultMsg?.id]);

  const { visibleSources, lowRelevanceSources } = useMemo(() => {
    const visible = [];
    const low = [];
    sourcesForCurrentResult.forEach((src, idx) => {
      const rel = formatRelevance(src.relevance_score);
      // Always show at least the top 2 sources (idx < 2)
      // Sources with relevance under 5% (0.05) are collapsed
      if (idx < 2 || rel.val >= 0.05) {
        visible.push({ source: src, rank: idx + 1 });
      } else {
        low.push({ source: src, rank: idx + 1 });
      }
    });
    return { visibleSources: visible, lowRelevanceSources: low };
  }, [sourcesForCurrentResult]);

  /* Submit */
  const handleSubmit = (e) => {
    e?.preventDefault();
    const q = (activeTab.draft || '').trim();
    if (!q || isTabLoading) return;
    sendMessage({ tabId: activeTab.id, queryText: q });
  };

  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleSubmit(e);
  };

  const handleCitationClick = (num) => {
    updateTab(activeTab.id, { evidenceTab: 'sources' });
    const targetRank = parseInt(num, 10);
    if (lowRelevanceSources.some((item) => item.rank === targetRank)) {
      setShowLowRelevance(true);
    }
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
    }, 120);
  };

  const handleRegenerate = (assistantMsgId) => {
    const msgs = activeTab.messages || [];
    const targetIdx = assistantMsgId
      ? msgs.findIndex((m) => m.id === assistantMsgId)
      : msgs.findLastIndex((m) => m.type === 'assistant');
    if (targetIdx === -1) return;

    const userMsg = [...msgs.slice(0, targetIdx)].reverse().find((m) => m.type === 'user');
    if (userMsg) {
      sendMessage({
        tabId: activeTab.id,
        queryText: userMsg.content,
        regenerateMessageId: msgs[targetIdx].id,
      });
    }
  };

  const clearConversation = () => {
    clearTab(activeTab.id);
  };

  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth <= 768
  );

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const [persistedLayout] = useState(() => getValidatedPanelLayout());

  const isMountedRef = useRef(false);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const handleLayoutChanged = useCallback((layout) => {
    if (!isMountedRef.current) return;
    if (!layout) return;
    const values = Object.values(layout).map(Number);
    if (values.length >= 2) {
      const [left, right] = values;
      if (left >= 30 && right >= 20 && !Number.isNaN(left) && !Number.isNaN(right)) {
        try {
          localStorage.setItem(PANEL_STORAGE_KEY, JSON.stringify(layout));
        } catch {}
      }
    }
  }, []);

  const evidenceTabs = [
    { value: 'sources', label: 'Sources', count: sourcesForCurrentResult.length },
    { value: 'tables', label: 'Tables', count: tablesInSources.length },
    { value: 'images', label: 'Images', count: imagesInSources.length },
    { value: 'trace', label: 'Trace' },
  ];

  return (
    <div className="query-page">
      <Group
        id="query-workspace-panels"
        orientation={isMobile ? 'vertical' : 'horizontal'}
        className="query-panels"
        defaultLayout={persistedLayout || undefined}
        onLayoutChanged={handleLayoutChanged}
      >
        {/* ── Left: Conversation ──────────────────────────────── */}
        <Panel id="conv-panel" defaultSize="60%" minSize="35%" className="conv-panel">
          <div className="conv-panel__inner">
            {/* Chrome-style Tab Strip */}
            <ChatTabStrip />

            {/* Conversation thread */}
            <div
              className="conv-thread"
              role="tabpanel"
              id={`tabpanel-${activeTab.id}`}
              aria-labelledby={`tab-${activeTab.id}`}
              aria-live="polite"
              aria-label={`Conversation - ${activeTab.title}`}
            >
              {messages.length === 0 && !isTabLoading && (
                <div className="conv-empty">
                  <EmptyState
                    icon={<MessageSquare size={24} />}
                    title="Ask anything"
                    description="Query your documents using multimodal RAG — text, tables, figures, and images."
                  />
                  <div className="suggested-prompts">
                    {SUGGESTED_PROMPTS.map((p) => (
                      <button
                        key={p}
                        type="button"
                        className="suggested-prompt"
                        onClick={() => {
                          updateTab(activeTab.id, { draft: p });
                          textareaRef.current?.focus();
                        }}
                      >
                        <Sparkles size={12} />
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg, i) => {
                if (msg.type === 'user') return <UserBubble key={msg.id || i} text={msg.content} />;
                return (
                  <AssistantBubble
                    key={msg.id || i}
                    msg={msg}
                    isActiveEvidence={activeResultMsg?.id === msg.id}
                    onSelectEvidence={() =>
                      updateTab(activeTab.id, { activeMessageId: msg.id })
                    }
                    onCitationClick={handleCitationClick}
                    onRegenerate={() => handleRegenerate(msg.id)}
                    onRevealed={() => markMessageRevealed(activeTab.id, msg.id)}
                  />
                );
              })}

              <div ref={bottomRef} />
            </div>

            {/* Pinned composer */}
            <div className="composer">
              {/* Deleted document inline notice */}
              {activeTab.docNotice && (
                <div className="doc-filter-notice" role="status">
                  <Info size={13} />
                  <span>{activeTab.docNotice}</span>
                  <button
                    type="button"
                    className="doc-filter-notice__dismiss"
                    onClick={() => updateTab(activeTab.id, { docNotice: null })}
                    aria-label="Dismiss notice"
                  >
                    <X size={12} />
                  </button>
                </div>
              )}

              {/* Doc filter chips */}
              {!docsLoading && documents.length > 0 && (
                <div className="composer__doc-chips">
                  {selectedDocs.map((id) => {
                    const doc = documents.find((d) => d.document_id === id);
                    if (!doc) return null;
                    return (
                      <span key={id} className="doc-filter-chip">
                        {doc.filename}
                        <button
                          type="button"
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
                    <button
                      type="button"
                      className="doc-filter-dropdown__btn"
                      aria-label="Select documents to filter"
                    >
                      Filter docs <ChevronDown size={11} />
                    </button>
                    <div className="doc-filter-dropdown__menu">
                      {documents.map((doc) => (
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
                    disabled={isTabLoading}
                    aria-label="Query input"
                  />
                </div>
                <div className="composer__footer">
                  <div className="composer__footer-left">
                    <select
                      className="model-select"
                      value={provider}
                      onChange={(e) => updateTab(activeTab.id, { model: e.target.value })}
                      disabled={isTabLoading}
                      aria-label="Select model"
                    >
                      {PROVIDER_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.provider} — {o.label}
                        </option>
                      ))}
                    </select>
                    {messages.length > 0 && (
                      <button
                        type="button"
                        className="clear-btn"
                        onClick={clearConversation}
                        aria-label="Clear conversation"
                      >
                        Clear
                      </button>
                    )}
                  </div>
                  <div className="composer__footer-right">
                    <span className="composer__hint">
                      <Kbd>Ctrl</Kbd>+<Kbd>Enter</Kbd>
                    </span>
                    <Button
                      id="query-submit-btn"
                      type="submit"
                      variant="primary"
                      size="md"
                      loading={isTabLoading}
                      disabled={!query.trim() || isTabLoading}
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
        <Panel id="evidence-panel" defaultSize="40%" minSize="25%" className="evidence-panel">
          <div className="evidence-panel__inner">
            <div className="evidence-panel__header">
              <Tabs
                tabs={evidenceTabs}
                active={evidenceTab}
                onChange={(tab) => updateTab(activeTab.id, { evidenceTab: tab })}
              />
            </div>

            <div className="evidence-panel__body">
              {/* While a query is pending: show skeleton state in evidence panel */}
              {isTabLoading && (
                <div className="evidence-skeleton">
                  <div className="skeleton" style={{ height: '22px', width: '45%', borderRadius: '6px' }} />
                  <div className="skeleton" style={{ height: '100px', borderRadius: '10px' }} />
                  <div className="skeleton" style={{ height: '100px', borderRadius: '10px' }} />
                  <div className="skeleton" style={{ height: '36px', width: '65%', borderRadius: '6px' }} />
                </div>
              )}

              {/* No result yet and not loading */}
              {!lastResult && !isTabLoading && (
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
                    <EmptyState
                      icon={<FileText size={20} />}
                      title="No sources"
                      description="No matching chunks were found for this query."
                    />
                  ) : (
                    <>
                      {visibleSources.map(({ source, rank }) => (
                        <SourceCard
                          key={source.chunk_id}
                          source={source}
                          rank={rank}
                          isHighlighted={highlighted === String(rank)}
                          allSources={sourcesForCurrentResult}
                          answer={lastResult?.answer}
                          query={lastResult?.query}
                        />
                      ))}

                      {lowRelevanceSources.length > 0 && (
                        <div className="low-relevance-section">
                          <button
                            type="button"
                            className={`low-relevance-toggle ${showLowRelevance ? 'low-relevance-toggle--expanded' : ''}`}
                            onClick={() => setShowLowRelevance((prev) => !prev)}
                            aria-expanded={showLowRelevance}
                            id="toggle-low-relevance-btn"
                          >
                            <ChevronDown
                              size={14}
                              className={`low-relevance-chevron ${showLowRelevance ? 'low-relevance-chevron--open' : ''}`}
                            />
                            <span>
                              {showLowRelevance
                                ? `Hide ${lowRelevanceSources.length} low-relevance sources`
                                : `Show ${lowRelevanceSources.length} low-relevance sources`}
                            </span>
                          </button>

                          {showLowRelevance && (
                            <div className="low-relevance-sources animate-fade-in">
                              {lowRelevanceSources.map(({ source, rank }) => (
                                <SourceCard
                                  key={source.chunk_id}
                                  source={source}
                                  rank={rank}
                                  isHighlighted={highlighted === String(rank)}
                                  allSources={sourcesForCurrentResult}
                                  answer={lastResult?.answer}
                                  query={lastResult?.query}
                                />
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* Tables tab */}
              {lastResult && evidenceTab === 'tables' && (
                <div className="tables-list">
                  {tablesInSources.length === 0 ? (
                    <EmptyState
                      icon={<Table2 size={20} />}
                      title="No tables"
                      description="No table chunks were retrieved for this query."
                    />
                  ) : (
                    tablesInSources.map((src) => (
                      <div key={src.chunk_id} className="table-chunk">
                        <div className="table-chunk__header">
                          <span>
                            Table from {src.filename} · p.{src.page + 1}
                          </span>
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
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {src.text_preview}
                          </ReactMarkdown>
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
                    <EmptyState
                      icon={<Image size={20} />}
                      title="No images"
                      description="No figure chunks were retrieved for this query."
                    />
                  ) : (
                    imagesInSources.map((src) => (
                      <div key={src.chunk_id} className="image-chunk">
                        <div className="image-chunk__header">
                          Figure from {src.filename} · p.{src.page + 1}
                        </div>
                        <div className="image-chunk__content">
                          {src.text_preview && (
                            <p className="image-chunk__caption">
                              {src.text_preview.slice(0, 200)}
                            </p>
                          )}
                          {src.bbox?.length === 4 && (
                            <div className="bbox-mini">
                              <svg viewBox="0 0 100 141" className="bbox-mini__svg">
                                <rect
                                  x="0"
                                  y="0"
                                  width="100"
                                  height="141"
                                  fill="var(--bg-elevated)"
                                  rx="2"
                                />
                                {[18, 26, 34, 42, 50, 58, 66, 74, 82, 90, 98, 106, 114, 122].map(
                                  (y) => (
                                    <line
                                      key={y}
                                      x1="8"
                                      y1={y}
                                      x2="92"
                                      y2={y}
                                      stroke="var(--border)"
                                      strokeWidth="0.8"
                                    />
                                  )
                                )}
                                <rect
                                  x={src.bbox[0] * 100}
                                  y={src.bbox[1] * 141}
                                  width={Math.max(src.bbox[2] - src.bbox[0], 0.02) * 100}
                                  height={Math.max(src.bbox[3] - src.bbox[1], 0.02) * 141}
                                  fill="rgba(255,181,71,0.2)"
                                  stroke="var(--warn)"
                                  strokeWidth="1.5"
                                  rx="1"
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
                  embedAttempts={lastResult.embed_attempts}
                  embedCacheHit={lastResult.embed_cache_hit}
                />
                )}
              </div>
            </div>
          </Panel>
        </Group>
      </div>
    );
  }

export default function QueryPage() {
  const { setActive } = useChat();
  const [viewKey, setViewKey] = useState(0);
  const containerRef = useRef(null);
  const remountAttemptedRef = useRef(false);

  const handleResetView = useCallback(() => {
    try {
      localStorage.removeItem(PANEL_STORAGE_KEY);
      localStorage.removeItem('rag-query-panels');
    } catch {}
    setActive('default');
    setViewKey((k) => k + 1);
  }, [setActive]);


  // STEP 3: Safety net: if the Query page root has zero height or width, or computed opacity 0,
  // 800 ms after mount in production, force a one-time remount of the content (key bump) and log a console.warn.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (remountAttemptedRef.current) return;
      const el = containerRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      const parent = el.closest('.shell__page') || el.parentElement;
      const parentStyle = parent ? window.getComputedStyle(parent) : null;

      const isZeroSize = rect.width === 0 || rect.height === 0;
      const isHiddenOpacity = style.opacity === '0' || parentStyle?.opacity === '0';
      const isNotDisplayed = style.display === 'none' || parentStyle?.display === 'none';

      if (isZeroSize || isHiddenOpacity || isNotDisplayed) {
        console.warn(
          '[QueryPage] Safety net triggered: zero dimensions or opacity 0 detected after 800ms. Forcing remount.',
          { rect: { width: rect.width, height: rect.height }, opacity: style.opacity, parentOpacity: parentStyle?.opacity }
        );
        if (parent && parentStyle?.opacity === '0') {
          parent.style.opacity = '1';
        }
        remountAttemptedRef.current = true;
        setViewKey((k) => k + 1);
      }
    }, 800);

    return () => clearTimeout(timer);
  }, [viewKey]);

  return (
    <div
      ref={containerRef}
      className="query-page-root"
      style={{
        height: '100%',
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
        minHeight: 0,
      }}
    >
      <QueryErrorBoundary onResetView={handleResetView}>
        <QueryPageInner key={viewKey} onResetView={handleResetView} />
      </QueryErrorBoundary>
    </div>
  );
}
