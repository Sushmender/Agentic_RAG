/**
 * EvaluationPage.jsx — Day 2 rebuild
 * Features:
 *   - K selector as segmented control (1, 3, 5, 10)
 *   - Run Evaluation pill button with accent glow
 *   - Running state: progress panel with elapsed timer + indeterminate bar
 *   - 4 hero StatCards: Recall/Precision before+after with colored delta
 *   - ComparisonBars chart (before vs after reranking)
 *   - Per-question results table with expandable rows
 *   - Export as JSON/CSV
 *   - Persist last result in localStorage with timestamp
 *   - Empty / error states
 */

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Play, Target, ChevronDown, ChevronRight,
  Download, FlaskConical, CheckCircle, XCircle,
  TrendingUp, TrendingDown, Minus, RefreshCw
} from 'lucide-react';
import { evaluationAPI } from '../services/api';

import { ComparisonBars } from '../components/charts/StageBars';
import './EvaluationPage.css';

const STORAGE_KEY = 'eval_last_result';
const fmtPct = (v) => (v == null ? '—' : `${(Number(v) * 100).toFixed(1)}%`);

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveToStorage(data) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {}
}

/* ── Delta badge ─────────────────────────────────────────────────────────── */
function DeltaBadge({ pre, post }) {
  if (pre == null || post == null) return null;
  const diff = post - pre;
  if (diff > 0.001)
    return (
      <span className="eval-delta eval-delta--up">
        <TrendingUp size={10} /> +{(diff * 100).toFixed(1)}%
      </span>
    );
  if (diff < -0.001)
    return (
      <span className="eval-delta eval-delta--down">
        <TrendingDown size={10} /> {(diff * 100).toFixed(1)}%
      </span>
    );
  return (
    <span className="eval-delta eval-delta--same">
      <Minus size={10} /> same
    </span>
  );
}

/* ── Running progress panel ──────────────────────────────────────────────── */
function RunningPanel({ elapsed }) {
  const stages = ['Embedding queries', 'Retrieving candidates', 'Reranking results', 'Computing metrics'];
  const stageIdx = Math.min(Math.floor(elapsed / 4), stages.length - 1);

  return (
    <motion.div
      className="eval-running-panel"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <div className="eval-running-icon">
        <FlaskConical size={24} className="animate-pulse" />
      </div>
      <div className="eval-running-content">
        <div className="eval-running-stage">{stages[stageIdx]}…</div>
        <div className="progress-bar" style={{ marginTop: 8 }}>
          <div className="progress-bar__fill--animated" />
        </div>
        <div className="eval-running-elapsed">
          Elapsed: {elapsed}s
        </div>
      </div>
    </motion.div>
  );
}

/* ── Expandable per-question row ─────────────────────────────────────────── */
function QuestionRow({ row, k, index }) {
  const [expanded, setExpanded] = useState(false);

  const recallImproved = row.post_rerank?.recall_at_k > row.pre_rerank?.recall_at_k + 0.001;
  const precImproved = row.post_rerank?.precision_at_k > row.pre_rerank?.precision_at_k + 0.001;
  const hit = recallImproved || precImproved;

  return (
    <>
      <motion.tr
        className={`eval-table__row ${expanded ? 'eval-table__row--expanded' : ''}`}
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: index * 0.03, duration: 0.2 }}
      >
        <td className="eval-td eval-td--idx">{index + 1}</td>
        <td className="eval-td eval-td--expand">
          <button
            className="eval-expand-btn"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            aria-label={expanded ? 'Collapse' : 'Expand row'}
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        </td>
        <td className="eval-td eval-td--question">{row.question}</td>
        <td className="eval-td">
          {hit ? (
            <span className="eval-hit-badge eval-hit-badge--hit">
              <CheckCircle size={12} /> Hit
            </span>
          ) : (
            <span className="eval-hit-badge eval-hit-badge--miss">
              <XCircle size={12} /> Miss
            </span>
          )}
        </td>
        <td className="eval-td mono eval-td--pre">{fmtPct(row.pre_rerank?.recall_at_k)}</td>
        <td className="eval-td mono eval-td--post">
          {fmtPct(row.post_rerank?.recall_at_k)}
          {recallImproved && <TrendingUp size={10} style={{ color: 'var(--accent)', marginLeft: 3 }} />}
        </td>
        <td className="eval-td mono eval-td--pre">{fmtPct(row.pre_rerank?.precision_at_k)}</td>
        <td className="eval-td mono eval-td--post">
          {fmtPct(row.post_rerank?.precision_at_k)}
          {precImproved && <TrendingUp size={10} style={{ color: 'var(--accent)', marginLeft: 3 }} />}
        </td>
      </motion.tr>
      {expanded && row.retrieved_chunks?.length && (
        <tr className="eval-table__detail-row">
          <td colSpan={8} className="eval-table__detail-cell">
            <div className="eval-chunks">
              <div className="eval-chunks__title">Retrieved chunks (top {k}):</div>
              {row.retrieved_chunks.slice(0, k).map((chunk, ci) => (
                <div key={ci} className="eval-chunk">
                  <span className="eval-chunk__rank mono">#{ci + 1}</span>
                  <span className="eval-chunk__text">{chunk.text || chunk.content || JSON.stringify(chunk)}</span>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

/* ── Main page ───────────────────────────────────────────────────────────── */
const K_OPTIONS = [1, 3, 5, 10];

export default function EvaluationPage() {
  const [k, setK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [report, setReport] = useState(() => {
    const saved = loadFromStorage();
    return saved?.report ?? null;
  });
  const [lastRunAt, setLastRunAt] = useState(() => {
    const saved = loadFromStorage();
    return saved?.lastRunAt ?? null;
  });
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  // Elapsed timer while running
  useEffect(() => {
    if (loading) {
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((e) => e + 1), 1000);
    } else {
      clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [loading]);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const res = await evaluationAPI.run(k);
      const data = res.data;
      setReport(data);
      const now = new Date().toISOString();
      setLastRunAt(now);
      saveToStorage({ report: data, lastRunAt: now });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (typeof detail === 'object' && detail?.error) {
        setError(detail.error + (detail.hint ? ` — ${detail.hint}` : ''));
      } else if (typeof detail === 'string') {
        setError(detail);
      } else {
        setError('Evaluation failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  // Export helpers
  const handleExportJSON = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `eval_k${report.k}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportCSV = () => {
    if (!report?.per_question?.length) return;
    const k_ = report.k;
    const headers = [
      'Question',
      `Pre Recall@${k_}`, `Post Recall@${k_}`,
      `Pre Precision@${k_}`, `Post Precision@${k_}`,
    ];
    const rows = report.per_question.map((row) => [
      `"${(row.question || '').replace(/"/g, '""')}"`,
      row.pre_rerank?.recall_at_k?.toFixed(4) ?? '',
      row.post_rerank?.recall_at_k?.toFixed(4) ?? '',
      row.pre_rerank?.precision_at_k?.toFixed(4) ?? '',
      row.post_rerank?.precision_at_k?.toFixed(4) ?? '',
    ]);
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `eval_k${report.k}_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const { pre_rerank, post_rerank, k: rK } = report ?? {};

  const comparisonData = report
    ? [
        { label: `Recall@${rK}`, before: pre_rerank?.recall_at_k, after: post_rerank?.recall_at_k },
        { label: `Precision@${rK}`, before: pre_rerank?.precision_at_k, after: post_rerank?.precision_at_k },
      ]
    : [];

  return (
    <div className="eval-page">
      {/* ── Header: actions and status only (P-7) ────────────────── */}
      <div className="eval-header">
        <div className="eval-header-status">
          {lastRunAt ? (
            <span className="eval-last-run">
              Last run: {new Date(lastRunAt).toLocaleString()}
            </span>
          ) : (
            <span className="eval-last-run">
              Select K and run evaluation benchmark
            </span>
          )}
        </div>

        <div className="eval-header-actions">
          {/* K segmented control */}
          <div className="eval-k-control">
            <span className="eval-k-label">K =</span>
            <div className="eval-k-tabs" role="group" aria-label="Select K value">
              {K_OPTIONS.map((n) => (
                <button
                  key={n}
                  className={`eval-k-tab ${k === n ? 'eval-k-tab--active' : ''}`}
                  onClick={() => setK(n)}
                  disabled={loading}
                  aria-pressed={k === n}
                  id={`eval-k-${n}`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          {/* Run button */}
          <button
            id="run-evaluation-btn"
            className={`eval-run-btn ${loading ? 'eval-run-btn--loading' : ''}`}
            onClick={handleRun}
            disabled={loading}
            aria-label={loading ? 'Evaluation running…' : 'Run Evaluation'}
          >
            {loading ? (
              <RefreshCw size={16} className="animate-spin" />
            ) : (
              <Play size={16} />
            )}
            {loading ? 'Running…' : 'Run Evaluation'}
          </button>
        </div>
      </div>

      {/* ── Error ──────────────────────────────────────────────── */}
      <AnimatePresence>
        {error && (
          <motion.div
            className="eval-error"
            role="alert"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <XCircle size={14} /> {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Running state ─────────────────────────────────────── */}
      <AnimatePresence>
        {loading && <RunningPanel elapsed={elapsed} />}
      </AnimatePresence>

      {/* ── No matching gold data state ────────────────────────── */}
      {!loading && report?.status === 'no_gold_data' && !error && (
        <motion.div
          className="eval-empty"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="eval-empty-icon">
            <Target size={48} opacity={0.3} />
          </div>
          <h3>No evaluation questions match your documents yet</h3>
          <p>
            The gold dataset contains benchmark questions for specific documents.
            Upload documents corresponding to the evaluation benchmark to view Recall@K and Precision@K scores.
          </p>
        </motion.div>
      )}

      {/* ── Initial empty state ─────────────────────────────────── */}
      {!loading && !report && !error && (
        <motion.div
          className="eval-empty"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="eval-empty-icon">
            <Target size={48} opacity={0.3} />
          </div>
          <h3>No evaluation results yet</h3>
          <p>
            Select a K value and click <strong>Run Evaluation</strong> to compute
            Recall@K and Precision@K on your gold dataset.
          </p>
        </motion.div>
      )}

      {/* ── Results ───────────────────────────────────────────── */}
      <AnimatePresence>
        {!loading && report && report.status !== 'no_gold_data' && (
          <motion.div
            className="eval-results"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
          >
            {/* 4 hero StatCards */}
            <section className="eval-section" aria-label="Results summary">
              <div className="eval-section-header">
                <h2 className="eval-section-title">
                  Results — K = {rK}
                  <span className="eval-section-sub">
                    ({report.questions_evaluated} questions)
                  </span>
                </h2>
                <div className="eval-export-btns">
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={handleExportJSON}
                    id="export-json-btn"
                    aria-label="Export as JSON"
                  >
                    <Download size={13} /> JSON
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={handleExportCSV}
                    id="export-csv-btn"
                    aria-label="Export as CSV"
                  >
                    <Download size={13} /> CSV
                  </button>
                </div>
              </div>

              <div className="eval-hero-cards">
                <div className="eval-hero-card eval-hero-card--pre">
                  <div className="eval-hero-card__label">Pre Recall@{rK}</div>
                  <div className="eval-hero-card__value mono">
                    {fmtPct(pre_rerank?.recall_at_k)}
                  </div>
                  <div className="eval-hero-card__sub">Before reranking</div>
                </div>
                <div className="eval-hero-card eval-hero-card--post">
                  <div className="eval-hero-card__label">Post Recall@{rK}</div>
                  <div className="eval-hero-card__value mono">
                    {fmtPct(post_rerank?.recall_at_k)}
                  </div>
                  <DeltaBadge pre={pre_rerank?.recall_at_k} post={post_rerank?.recall_at_k} />
                </div>
                <div className="eval-hero-card eval-hero-card--pre">
                  <div className="eval-hero-card__label">Pre Precision@{rK}</div>
                  <div className="eval-hero-card__value mono">
                    {fmtPct(pre_rerank?.precision_at_k)}
                  </div>
                  <div className="eval-hero-card__sub">Before reranking</div>
                </div>
                <div className="eval-hero-card eval-hero-card--post">
                  <div className="eval-hero-card__label">Post Precision@{rK}</div>
                  <div className="eval-hero-card__value mono">
                    {fmtPct(post_rerank?.precision_at_k)}
                  </div>
                  <DeltaBadge pre={pre_rerank?.precision_at_k} post={post_rerank?.precision_at_k} />
                </div>
              </div>
            </section>

            {/* ComparisonBars chart */}
            {comparisonData.length > 0 && (
              <section className="eval-section" aria-label="Before vs after comparison chart">
                <h2 className="eval-section-title">Before vs After Reranking</h2>
                <ComparisonBars data={comparisonData} height={200} />
              </section>
            )}

            {/* Per-question table */}
            {report.per_question?.length > 0 && (
              <section className="eval-section eval-section--table" aria-label="Per-question breakdown">
                <h2 className="eval-section-title">
                  Per-Question Breakdown
                  <span className="eval-section-sub">
                    ({report.per_question.length} questions) · click row to expand chunks
                  </span>
                </h2>
                <div className="eval-table-scroll">
                  <table className="eval-table" aria-label="Per-question evaluation results">
                    <thead>
                      <tr>
                        <th className="eval-th">#</th>
                        <th className="eval-th"></th>
                        <th className="eval-th">Question</th>
                        <th className="eval-th">Result</th>
                        <th className="eval-th eval-th--pre">Pre Recall@{rK}</th>
                        <th className="eval-th eval-th--post">Post Recall@{rK}</th>
                        <th className="eval-th eval-th--pre">Pre Prec@{rK}</th>
                        <th className="eval-th eval-th--post">Post Prec@{rK}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.per_question.map((row, i) => (
                        <QuestionRow key={i} row={row} k={rK} index={i} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
