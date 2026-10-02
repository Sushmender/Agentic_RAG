/**
 * frontend/src/pages/MetricsPage.jsx
 * Day 7 — Observability dashboard.
 * Fetches from GET /api/v1/metrics and displays all 5 benchmark categories.
 * Auto-refreshes every 30 seconds.
 */

import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import './MetricsPage.css';

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(val, decimals = 1) {
  if (val == null || isNaN(val)) return '—';
  return Number(val).toFixed(decimals);
}

function fmtMs(ms) {
  if (!ms || ms < 1) return '< 1 ms';
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  return `${fmt(ms)} ms`;
}

function fmtUsd(usd) {
  if (!usd) return '$0.000000';
  return `$${Number(usd).toFixed(6)}`;
}

function fmtPct(rate) {
  return `${(rate * 100).toFixed(1)}%`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MetricCard({ icon, label, value, sub, accent }) {
  return (
    <div className={`metric-card ${accent ? 'metric-card--accent' : ''}`}>
      <div className="metric-card__icon">{icon}</div>
      <div className="metric-card__body">
        <div className="metric-card__value">{value}</div>
        <div className="metric-card__label">{label}</div>
        {sub && <div className="metric-card__sub">{sub}</div>}
      </div>
    </div>
  );
}

function LatencyBar({ label, ms, maxMs, color }) {
  const pct = maxMs > 0 ? Math.min((ms / maxMs) * 100, 100) : 0;
  return (
    <div className="latency-row">
      <span className="latency-row__label">{label}</span>
      <div className="latency-row__track">
        <div
          className="latency-row__fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="latency-row__value">{fmtMs(ms)}</span>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MetricsPage() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const REFRESH_INTERVAL = 30_000; // 30s

  const fetchMetrics = useCallback(async () => {
    try {
      const res = await api.get('/metrics');
      setMetrics(res.data);
      setLastRefresh(new Date());
      setError(null);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to load metrics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    const id = setInterval(fetchMetrics, REFRESH_INTERVAL);
    return () => clearInterval(id);
  }, [fetchMetrics]);

  // ── Stage latency chart max ─────────────────────────────────────────────────
  const stages = metrics?.latency_by_stage ?? {};
  const maxStageMs = Math.max(
    stages.embedding_ms ?? 0,
    stages.retrieval_ms ?? 0,
    stages.reranking_ms ?? 0,
    stages.llm_ms ?? 0,
    stages.ade_ms ?? 0,
    1,
  );

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="metrics-page">
      <div className="metrics-header">
        <div>
          <h1 className="metrics-title">📊 Observability Dashboard</h1>
          <p className="metrics-subtitle">
            Real-time pipeline telemetry — auto-refreshes every 30 s
          </p>
        </div>
        <div className="metrics-header-right">
          {lastRefresh && (
            <span className="metrics-last-refresh">
              Last refresh: {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            className="metrics-refresh-btn"
            onClick={() => { setLoading(true); fetchMetrics(); }}
            disabled={loading}
            title="Refresh metrics now"
          >
            {loading ? '↻ Loading…' : '↻ Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div className="metrics-error">
          ⚠️ {error}
        </div>
      )}

      {loading && !metrics && (
        <div className="metrics-loading">
          <div className="metrics-spinner" />
          <span>Loading telemetry…</span>
        </div>
      )}

      {metrics && (
        <>
          {/* ── Overview cards ─────────────────────────────────────────── */}
          <section className="metrics-section">
            <h2 className="metrics-section-title">Overview</h2>
            <div className="metrics-grid">
              <MetricCard
                icon="🔍"
                label="Total Queries"
                value={metrics.query_count.toLocaleString()}
                sub={`${metrics.ingestion_count} ingestions`}
                accent
              />
              <MetricCard
                icon="⚡"
                label="Cache Hit Rate"
                value={fmtPct(metrics.cache_hit_rate)}
                sub={`${metrics.cache_hit_count} hits`}
                accent
              />
              <MetricCard
                icon="📄"
                label="Records Analysed"
                value={metrics.records_analyzed.toLocaleString()}
                sub={
                  metrics.oldest_record_ts
                    ? `Since ${new Date(metrics.oldest_record_ts).toLocaleDateString()}`
                    : 'No records yet'
                }
              />
            </div>
          </section>

          {/* ── Latency cards ──────────────────────────────────────────── */}
          <section className="metrics-section">
            <h2 className="metrics-section-title">Latency</h2>
            <div className="metrics-grid">
              <MetricCard
                icon="⏱"
                label="Avg End-to-End"
                value={fmtMs(metrics.avg_latency_ms)}
                accent
              />
              <MetricCard
                icon="📈"
                label="p95 Latency"
                value={fmtMs(metrics.p95_latency_ms)}
              />
            </div>

            {/* Latency breakdown bar chart */}
            <div className="latency-chart">
              <h3 className="latency-chart__title">Avg per-stage breakdown (query records)</h3>
              <LatencyBar label="🔢 Embedding"  ms={stages.embedding_ms}  maxMs={maxStageMs} color="var(--color-embed)" />
              <LatencyBar label="🔍 Retrieval"  ms={stages.retrieval_ms}  maxMs={maxStageMs} color="var(--color-retrieve)" />
              <LatencyBar label="🏆 Reranking"  ms={stages.reranking_ms} maxMs={maxStageMs} color="var(--color-rerank)" />
              <LatencyBar label="🤖 LLM"         ms={stages.llm_ms}        maxMs={maxStageMs} color="var(--color-llm)" />
              <LatencyBar label="📑 ADE"          ms={stages.ade_ms}        maxMs={maxStageMs} color="var(--color-ade)" />
            </div>
          </section>

          {/* ── Cost & usage ───────────────────────────────────────────── */}
          <section className="metrics-section">
            <h2 className="metrics-section-title">Cost &amp; Usage</h2>
            <div className="metrics-grid">
              <MetricCard
                icon="🪙"
                label="Total LLM Cost"
                value={fmtUsd(metrics.total_llm_cost_usd)}
                sub="Groq + OpenRouter"
                accent
              />
              <MetricCard
                icon="🧮"
                label="Total Embedding Cost"
                value={fmtUsd(metrics.total_embedding_cost_usd)}
                sub="OpenRouter NVIDIA"
              />
              <MetricCard
                icon="💰"
                label="Total Cost"
                value={fmtUsd(metrics.total_cost_usd)}
                sub="Embedding + LLM"
              />
              <MetricCard
                icon="📝"
                label="Total Tokens"
                value={metrics.total_tokens.toLocaleString()}
                sub="Input + output"
              />
            </div>
          </section>

          {/* ── ADE ────────────────────────────────────────────────────── */}
          <section className="metrics-section">
            <h2 className="metrics-section-title">ADE Credits</h2>
            <div className="metrics-grid">
              <MetricCard
                icon="🏦"
                label="Total ADE Credits Used"
                value={fmt(metrics.total_ade_credits, 2)}
                sub={`Across ${metrics.ingestion_count} ingestion(s)`}
                accent
              />
            </div>
          </section>
        </>
      )}
    </div>
  );
}
