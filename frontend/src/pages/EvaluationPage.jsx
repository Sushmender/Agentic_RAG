/**
 * frontend/src/pages/EvaluationPage.jsx
 * Day 8 — RAG Evaluation page.
 *
 * Features:
 *   - K selector (1–10)
 *   - "Run Evaluation" button → GET /evaluation/run?k=N
 *   - Loading skeleton while running
 *   - Aggregate metric cards: pre/post Recall@K and Precision@K with improvement badge
 *   - Per-question breakdown table with all 4 metric columns
 *   - Error handling (empty ChromaDB, network errors)
 */

import { useState } from 'react';
import { evaluationAPI } from '../services/api';
import './EvaluationPage.css';

/* ── Helpers ──────────────────────────────────────────────────────────────── */
const fmtPct = (v) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);

function ImprovementBadge({ pre, post }) {
  if (pre == null || post == null) return null;
  const diff = post - pre;
  if (diff > 0.001)  return <span className="eval-improvement eval-improvement--up">▲ +{(diff * 100).toFixed(1)}%</span>;
  if (diff < -0.001) return <span className="eval-improvement eval-improvement--same">▼ {(diff * 100).toFixed(1)}%</span>;
  return <span className="eval-improvement eval-improvement--same">— same</span>;
}

/* ── Skeleton ─────────────────────────────────────────────────────────────── */
function EvalSkeleton() {
  return (
    <div className="eval-skeleton">
      <div className="eval-aggregate" style={{ marginBottom: '1.5rem' }}>
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="eval-skeleton-card" />
        ))}
      </div>
      <div className="eval-skeleton-table" />
    </div>
  );
}

/* ── Aggregate Cards ──────────────────────────────────────────────────────── */
function AggregateCards({ report }) {
  const { k, questions_evaluated, pre_rerank, post_rerank } = report;

  return (
    <div className="eval-aggregate">
      {/* Questions evaluated */}
      <div className="eval-metric-card eval-metric-card--info">
        <div className="eval-metric-card__label">Questions Evaluated</div>
        <div className="eval-metric-card__value">{questions_evaluated}</div>
        <div className="eval-metric-card__sub">at K = {k}</div>
      </div>

      {/* Pre-rerank Recall */}
      <div className="eval-metric-card eval-metric-card--pre">
        <div className="eval-metric-card__label">Pre-Rerank Recall@{k}</div>
        <div className="eval-metric-card__value">{fmtPct(pre_rerank?.recall_at_k)}</div>
        <div className="eval-metric-card__sub">Before reranking</div>
      </div>

      {/* Post-rerank Recall */}
      <div className="eval-metric-card eval-metric-card--post">
        <div className="eval-metric-card__label">Post-Rerank Recall@{k}</div>
        <div className="eval-metric-card__value">
          {fmtPct(post_rerank?.recall_at_k)}
          <ImprovementBadge pre={pre_rerank?.recall_at_k} post={post_rerank?.recall_at_k} />
        </div>
        <div className="eval-metric-card__sub">After reranking</div>
      </div>

      {/* Pre-rerank Precision */}
      <div className="eval-metric-card eval-metric-card--pre">
        <div className="eval-metric-card__label">Pre-Rerank Precision@{k}</div>
        <div className="eval-metric-card__value">{fmtPct(pre_rerank?.precision_at_k)}</div>
        <div className="eval-metric-card__sub">Before reranking</div>
      </div>

      {/* Post-rerank Precision */}
      <div className="eval-metric-card eval-metric-card--post">
        <div className="eval-metric-card__label">Post-Rerank Precision@{k}</div>
        <div className="eval-metric-card__value">
          {fmtPct(post_rerank?.precision_at_k)}
          <ImprovementBadge pre={pre_rerank?.precision_at_k} post={post_rerank?.precision_at_k} />
        </div>
        <div className="eval-metric-card__sub">After reranking</div>
      </div>
    </div>
  );
}

/* ── Per-question table ───────────────────────────────────────────────────── */
function PerQuestionTable({ perQuestion, k }) {
  if (!perQuestion?.length) return null;

  return (
    <section>
      <h2 className="eval-section-title">
        📋 Per-Question Breakdown
        <span style={{ color: '#64748b', fontWeight: 400, fontSize: '0.82rem' }}>
          ({perQuestion.length} question{perQuestion.length !== 1 ? 's' : ''})
        </span>
      </h2>
      <div className="eval-table-wrap">
        <table className="eval-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Question</th>
              <th>Pre Recall@{k}</th>
              <th>Pre Prec@{k}</th>
              <th>Post Recall@{k}</th>
              <th>Post Prec@{k}</th>
            </tr>
          </thead>
          <tbody>
            {perQuestion.map((row, i) => (
              <tr key={i}>
                <td style={{ color: '#64748b', fontSize: '0.8rem' }}>{i + 1}</td>
                <td className="eval-table__question">
                  {row.question}
                  {row.error && (
                    <div className="eval-table__error">⚠ {row.error}</div>
                  )}
                </td>
                {/* Pre-rerank */}
                <td className="eval-metric-cell eval-metric-cell--blue">
                  {fmtPct(row.pre_rerank?.recall_at_k)}
                </td>
                <td className="eval-metric-cell eval-metric-cell--blue">
                  {fmtPct(row.pre_rerank?.precision_at_k)}
                </td>
                {/* Post-rerank */}
                <td className="eval-metric-cell eval-metric-cell--green">
                  {fmtPct(row.post_rerank?.recall_at_k)}
                  {row.post_rerank?.recall_at_k > row.pre_rerank?.recall_at_k + 0.001 && (
                    <span className="eval-metric-cell__improvement">▲</span>
                  )}
                </td>
                <td className="eval-metric-cell eval-metric-cell--green">
                  {fmtPct(row.post_rerank?.precision_at_k)}
                  {row.post_rerank?.precision_at_k > row.pre_rerank?.precision_at_k + 0.001 && (
                    <span className="eval-metric-cell__improvement">▲</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* ── Main page component ──────────────────────────────────────────────────── */
export default function EvaluationPage() {
  const [k, setK]           = useState(5);
  const [loading, setLoading] = useState(false);
  const [report, setReport]   = useState(null);
  const [error, setError]     = useState(null);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setReport(null);

    try {
      const res = await evaluationAPI.run(k);
      setReport(res.data);
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

  return (
    <div className="eval-page">
      {/* ── Header ── */}
      <div className="eval-header">
        <div>
          <h1 className="eval-title">🎯 RAG Evaluation</h1>
          <p className="eval-subtitle">
            Measure Recall@K and Precision@K before and after reranking on the gold dataset
          </p>
        </div>
        <button
          id="run-evaluation-btn"
          className={`eval-run-btn ${loading ? 'eval-run-btn--loading' : ''}`}
          onClick={handleRun}
          disabled={loading}
        >
          {loading ? '⏳ Running…' : '▶ Run Evaluation'}
        </button>
      </div>

      {/* ── K selector ── */}
      <div className="eval-k-control">
        <label htmlFor="k-select">Evaluate at K =</label>
        <select
          id="k-select"
          className="eval-k-select"
          value={k}
          onChange={e => setK(Number(e.target.value))}
          disabled={loading}
        >
          {[1, 2, 3, 4, 5, 7, 10].map(n => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
        <span>(top-{k} candidates considered)</span>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="eval-error" role="alert">
          ⚠ {error}
        </div>
      )}

      {/* ── Loading skeleton ── */}
      {loading && <EvalSkeleton />}

      {/* ── No data yet ── */}
      {!loading && !report && !error && (
        <div className="eval-empty">
          <div className="eval-empty-icon">📊</div>
          <h3>No evaluation results yet</h3>
          <p>Click "Run Evaluation" to compute Recall@{k} and Precision@{k} on the gold dataset.</p>
        </div>
      )}

      {/* ── Results ── */}
      {!loading && report && (
        <>
          <AggregateCards report={report} />
          <PerQuestionTable perQuestion={report.per_question} k={report.k} />
        </>
      )}
    </div>
  );
}
