/**
 * MetricsPage.jsx — Day 2 rebuild
 * Analytics-grade Observability dashboard
 * Features:
 *   - StatCards (count-up animation) for key KPIs
 *   - RingChart for cache hit rate
 *   - StageBars for per-stage latency breakdown with insight
 *   - Cost & usage panel
 *   - Recent queries table with sort, filter, row drawer
 *   - Time-range tabs (Today / Yesterday / This week) — client-side filter
 *   - Auto-refresh every 30s with countdown + manual refresh
 *   - Skeleton, empty, error states
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RefreshCw, Clock, Zap, Database, TrendingUp,
  DollarSign, Hash, BarChart3, X, ChevronUp,
  ChevronDown, Search, MessageSquare
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { StatCard } from '../components/charts/StatCard';
import { RingChart } from '../components/charts/RingChart';
import { StageBar } from '../components/charts/StageBars';
import './MetricsPage.css';

/* ── Helpers ────────────────────────────────────────────────────────────── */
const fmt = (v, d = 1) => (v == null || isNaN(v) ? '—' : Number(v).toFixed(d));
const fmtMs = (ms) => {
  if (!ms && ms !== 0) return '—';
  if (ms < 1) return '< 1 ms';
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  return `${fmt(ms)} ms`;
};
const fmtCost = (usd) => {
  if (usd == null || isNaN(usd)) return { display: '—', full: '—' };
  const num = Number(usd);
  if (num === 0) return { display: '$0.00', full: '$0.000000' };
  const full = `$${num.toFixed(6)}`;
  let display;
  if (num >= 100) display = `$${num.toFixed(2)}`;
  else if (num >= 1) display = `$${num.toFixed(2)}`;
  else if (num >= 0.01) display = `$${num.toFixed(3)}`;
  else if (num >= 0.0001) display = `$${num.toFixed(4)}`;
  else display = `< $0.0001`;
  return { display, full };
};
const fmtUsd = (usd) => fmtCost(usd).display;

/* ── Skeleton grid ──────────────────────────────────────────────────────── */
function SkeletonGrid({ count = 4 }) {
  return (
    <div className="metrics-skeleton-grid">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 96 }} />
      ))}
    </div>
  );
}

/* ── Drawer for per-row trace ───────────────────────────────────────────── */
function TraceDrawer({ row, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const stages = [
    { label: 'Embedding',  ms: row.embedding_ms,  color: 'var(--color-embed)' },
    { label: 'Retrieval',  ms: row.retrieval_ms,  color: 'var(--color-retrieve)' },
    { label: 'Reranking',  ms: row.reranking_ms,  color: 'var(--color-rerank)' },
    { label: 'LLM',        ms: row.llm_ms,        color: 'var(--color-llm)' },
    { label: 'ADE',        ms: row.ade_ms,        color: 'var(--color-ade)' },
  ].filter((s) => s.ms != null && s.ms > 0);
  const maxMs = Math.max(...stages.map((s) => s.ms), 1);

  return (
    <motion.div
      className="trace-drawer-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Query trace details"
    >
      <motion.div
        className="trace-drawer"
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="trace-drawer__header">
          <span className="trace-drawer__title">Query Trace</span>
          <button
            className="trace-drawer__close"
            onClick={onClose}
            aria-label="Close trace drawer"
          >
            <X size={16} />
          </button>
        </div>

        <div className="trace-drawer__body">
          <div className="trace-drawer__question">{row.question || row.query || '—'}</div>

          <div className="trace-drawer__meta">
            {row.model && (
              <span className="badge badge-accent2">{row.model}</span>
            )}
            {row.cache_hit && (
              <span className="badge badge-info">Cache hit</span>
            )}
            {row.total_cost_usd != null && (
              <span className="badge badge-neutral">{fmtUsd(row.total_cost_usd)}</span>
            )}
          </div>

          <div className="trace-drawer__section-title">Pipeline Timings</div>
          <div className="trace-drawer__stages">
            {stages.length > 0 ? (
              stages.map((s) => (
                <StageBar
                  key={s.label}
                  label={s.label}
                  value={s.ms}
                  displayValue={fmtMs(s.ms)}
                  maxValue={maxMs}
                  color={s.color}
                />
              ))
            ) : (
              <p className="trace-drawer__empty">No stage timing data available.</p>
            )}
          </div>

          {row.total_latency_ms != null && (
            <div className="trace-drawer__total">
              <span>Total E2E</span>
              <span className="mono">{fmtMs(row.total_latency_ms)}</span>
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

function TableSortIcon({ k, sortKey, sortDir }) {
  if (sortKey !== k) return <ChevronDown size={12} opacity={0.3} />;
  return sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />;
}

/* ── Recent Queries Table ───────────────────────────────────────────────── */
function QueriesTable({ records, navigate }) {
  const [sortKey, setSortKey] = useState('timestamp');
  const [sortDir, setSortDir] = useState('desc');
  const [filter, setFilter] = useState('');
  const [selected, setSelected] = useState(null);

  const handleSort = (key) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  };

  const filtered = useMemo(() => {
    const q = filter.toLowerCase();
    return (records || []).filter((r) =>
      !q ||
      (r.question || r.query || '').toLowerCase().includes(q) ||
      (r.model || '').toLowerCase().includes(q)
    );
  }, [records, filter]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (av == null) av = sortDir === 'asc' ? Infinity : -Infinity;
      if (bv == null) bv = sortDir === 'asc' ? Infinity : -Infinity;
      if (typeof av === 'string') return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortDir === 'asc' ? av - bv : bv - av;
    });
  }, [filtered, sortKey, sortDir]);

  if (!records?.length) {
    return (
      <div className="metrics-empty-queries">
        <MessageSquare size={36} opacity={0.3} />
        <p>No queries yet — ask your first question</p>
        <button
          className="btn btn-primary"
          onClick={() => navigate('/query')}
          id="go-to-query-btn"
        >
          Go to Query
        </button>
      </div>
    );
  }

  return (
    <div className="queries-table-wrap">
      <div className="queries-table-toolbar">
        <div className="queries-table-search">
          <Search size={14} />
          <input
            type="search"
            placeholder="Filter queries…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="queries-table-search__input"
            aria-label="Filter queries"
          />
        </div>
        <span className="queries-table-count">
          {filtered.length} / {records.length} records
        </span>
      </div>

      <div className="queries-table-scroll">
        <table className="queries-table" aria-label="Recent queries">
          <thead>
            <tr>
              <th
                className="queries-table__th sortable"
                onClick={() => handleSort('timestamp')}
                aria-sort={sortKey === 'timestamp' ? sortDir : 'none'}
              >
                Time <TableSortIcon k="timestamp" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="queries-table__th">Question</th>
              <th
                className="queries-table__th sortable"
                onClick={() => handleSort('model')}
                aria-sort={sortKey === 'model' ? sortDir : 'none'}
              >
                Model <TableSortIcon k="model" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th
                className="queries-table__th sortable"
                onClick={() => handleSort('total_latency_ms')}
                aria-sort={sortKey === 'total_latency_ms' ? sortDir : 'none'}
              >
                Latency <TableSortIcon k="total_latency_ms" sortKey={sortKey} sortDir={sortDir} />
              </th>
              <th className="queries-table__th">Cache</th>
              <th
                className="queries-table__th sortable"
                onClick={() => handleSort('total_cost_usd')}
                aria-sort={sortKey === 'total_cost_usd' ? sortDir : 'none'}
              >
                Cost <TableSortIcon k="total_cost_usd" sortKey={sortKey} sortDir={sortDir} />
              </th>
            </tr>
          </thead>
          <tbody>
            <AnimatePresence initial={false}>
              {sorted.map((row, i) => (
                <motion.tr
                  key={row.id ?? i}
                  className="queries-table__row"
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.025, duration: 0.2 }}
                  onClick={() => setSelected(row)}
                  title="Click for full trace"
                >
                  <td className="queries-table__td mono">
                    {row.timestamp
                      ? new Date(row.timestamp).toLocaleTimeString()
                      : '—'}
                  </td>
                  <td className="queries-table__td queries-table__question">
                    {(row.question || row.query || '—').slice(0, 80)}
                    {(row.question || row.query || '').length > 80 ? '…' : ''}
                  </td>
                  <td className="queries-table__td">
                    {row.model ? (
                      <span className="badge badge-accent2">{row.model}</span>
                    ) : '—'}
                  </td>
                  <td className="queries-table__td mono">
                    {fmtMs(row.total_latency_ms)}
                  </td>
                  <td className="queries-table__td">
                    {row.cache_hit ? (
                      <span className="badge badge-info">Hit</span>
                    ) : (
                      <span className="badge badge-neutral">Miss</span>
                    )}
                  </td>
                  <td className="queries-table__td mono">
                    {fmtUsd(row.total_cost_usd)}
                  </td>
                </motion.tr>
              ))}
            </AnimatePresence>
          </tbody>
        </table>
      </div>

      <AnimatePresence>
        {selected && (
          <TraceDrawer row={selected} onClose={() => setSelected(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── Time range filter ──────────────────────────────────────────────────── */
const TIME_TABS = [
  { id: 'today',     label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: 'week',      label: 'This week' },
  { id: 'all',       label: 'All time' },
];

function filterByTime(records, tab) {
  if (!records?.length || tab === 'all') return records || [];
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart); yesterdayStart.setDate(todayStart.getDate() - 1);
  const weekStart = new Date(todayStart); weekStart.setDate(todayStart.getDate() - 7);

  return records.filter((r) => {
    if (!r.timestamp) return tab === 'all';
    const t = new Date(r.timestamp);
    if (tab === 'today') return t >= todayStart;
    if (tab === 'yesterday') return t >= yesterdayStart && t < todayStart;
    if (tab === 'week') return t >= weekStart;
    return true;
  });
}

function hasTimestamps(records) {
  return records?.some((r) => r.timestamp != null) ?? false;
}

/* ── Main page ──────────────────────────────────────────────────────────── */
export default function MetricsPage() {
  const navigate = useNavigate();
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [countdown, setCountdown] = useState(30);
  const [timeTab, setTimeTab] = useState('all');
  const REFRESH_INTERVAL = 30_000;

  const fetchMetrics = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const res = await api.get('/metrics');
      setMetrics(res.data);
      setLastRefresh(new Date());
      setError(null);
      setCountdown(30);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to load metrics');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    const id = setInterval(() => fetchMetrics(), REFRESH_INTERVAL);
    return () => clearInterval(id);
  }, [fetchMetrics]);

  // Countdown ticker
  useEffect(() => {
    const id = setInterval(() => {
      setCountdown((c) => (c <= 1 ? 30 : c - 1));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // Derived data
  const stages = metrics?.latency_by_stage ?? {};
  const stageList = [
    { label: 'Embedding',  ms: stages.embedding_ms,  color: 'var(--color-embed)' },
    { label: 'Retrieval',  ms: stages.retrieval_ms,  color: 'var(--color-retrieve)' },
    { label: 'Reranking',  ms: stages.reranking_ms,  color: 'var(--color-rerank)' },
    { label: 'LLM',        ms: stages.llm_ms,        color: 'var(--color-llm)' },
    { label: 'ADE',        ms: stages.ade_ms,        color: 'var(--color-ade)' },
  ].filter((s) => s.ms != null).sort((a, b) => b.ms - a.ms);

  const maxStageMs = Math.max(...stageList.map((s) => s.ms), 1);
  const totalStageMs = stageList.reduce((acc, s) => acc + s.ms, 0);

  const topStage = stageList[0];
  const stageInsight = topStage && totalStageMs > 0
    ? `${topStage.label} accounts for ${Math.round((topStage.ms / totalStageMs) * 100)}% of pipeline time`
    : null;

  const records = metrics?.recent_queries ?? [];
  const showTimeTabs = hasTimestamps(records);
  const filteredRecords = filterByTime(records, timeTab);

  const cacheHitPct = metrics?.cache_hit_rate != null
    ? (metrics.cache_hit_rate * 100).toFixed(1)
    : null;

  const totalQueries = metrics?.query_count ?? 0;
  const hitCount = metrics?.cache_hit_count ?? 0;
  const missCount = Math.max(0, totalQueries - hitCount);
  const hitLabel = `${hitCount} ${hitCount === 1 ? 'hit' : 'hits'}`;
  const missLabel = `${missCount} ${missCount === 1 ? 'miss' : 'misses'}`;

  const llmCost = fmtCost(metrics?.total_llm_cost_usd);
  const embedCost = fmtCost(metrics?.total_embedding_cost_usd);
  const totalCost = fmtCost(metrics?.total_cost_usd);

  return (
    <div className="metrics-page">
      {/* ── Page header: actions and status only (P-7) ──────────────── */}
      <div className="metrics-header">
        <div className="metrics-header-status">
          {lastRefresh && (
            <span className="metrics-last-refresh">
              <Clock size={12} />
              Updated {lastRefresh.toLocaleTimeString()} · auto-refresh in {countdown}s
            </span>
          )}
        </div>
        <div className="metrics-header-controls">
          <button
            id="metrics-refresh-btn"
            className={`btn btn-secondary btn-sm ${refreshing ? 'btn-loading' : ''}`}
            onClick={() => fetchMetrics(true)}
            disabled={loading || refreshing}
            aria-label="Refresh metrics"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* ── Error banner ─────────────────────────────────────────── */}
      <AnimatePresence>
        {error && (
          <motion.div
            className="metrics-error"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            role="alert"
          >
            <Zap size={14} /> {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Loading ───────────────────────────────────────────────── */}
      {loading && !metrics && (
        <div className="metrics-loading-wrap">
          <SkeletonGrid count={5} />
          <SkeletonGrid count={3} />
        </div>
      )}

      {/* ── Main content ─────────────────────────────────────────── */}
      {metrics && (
        <motion.div
          className="metrics-content"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        >
          {/* ── Overview row (P-4: single level surface) ───────── */}
          <section className="metrics-section metrics-section--overview" aria-label="Overview">
            <div className="metrics-kpi-row">
              {/* Stat cards */}
              <div className="metrics-stat-cards">
                <StatCard
                  icon={Database}
                  label="Total Queries"
                  rawValue={metrics.query_count}
                  value={metrics.query_count?.toLocaleString()}
                  sub={`${metrics.ingestion_count ?? 0} ingestions`}
                  accent
                />
                <StatCard
                  icon={TrendingUp}
                  label="Records Analysed"
                  rawValue={metrics.records_analyzed}
                  value={metrics.records_analyzed?.toLocaleString()}
                  sub={
                    metrics.oldest_record_ts
                      ? `Since ${new Date(metrics.oldest_record_ts).toLocaleDateString()}`
                      : undefined
                  }
                />
                <StatCard
                  icon={Clock}
                  label="Avg End-to-End"
                  value={fmtMs(metrics.avg_latency_ms)}
                  accent
                />
                <StatCard
                  icon={BarChart3}
                  label="P95 Latency"
                  value={fmtMs(metrics.p95_latency_ms)}
                />
              </div>

              {/* Cache hit rate ring (P-3) */}
              <div className="metrics-ring-card">
                <div className="metrics-ring-card__title">Cache Hit Rate</div>
                <div className="metrics-ring-card__chart">
                  <RingChart
                    percent={cacheHitPct != null ? Number(cacheHitPct) : 0}
                    centerLabel={cacheHitPct != null ? `${cacheHitPct}%` : '—'}
                    centerSub="hit rate"
                    size={130}
                  />
                </div>
                <div className="metrics-ring-card__sub">
                  {hitLabel} · {missLabel}
                </div>
              </div>
            </div>
          </section>

          {/* ── Latency breakdown ────────────────────────────────── */}
          <section className="metrics-section" aria-label="Latency breakdown">
            <div className="metrics-section-header">
              <h2 className="metrics-section-title">Latency Breakdown</h2>
              {stageInsight && (
                <span className="metrics-insight">💡 {stageInsight}</span>
              )}
            </div>
            <div className="metrics-latency-panel">
              <div className="metrics-latency-bars">
                {stageList.length > 0 ? (
                  stageList.map((s) => (
                    <StageBar
                      key={s.label}
                      label={s.label}
                      value={s.ms}
                      displayValue={fmtMs(s.ms)}
                      maxValue={maxStageMs}
                      color={s.color}
                    />
                  ))
                ) : (
                  <p className="metrics-no-data">No stage timing data yet</p>
                )}
              </div>
              <div className="metrics-latency-side">
                <div className="metrics-latency-comparison">
                  <div className="metrics-latency-comparison__row">
                    <span>Avg E2E</span>
                    <span className="mono">{fmtMs(metrics.avg_latency_ms)}</span>
                  </div>
                  <div className="metrics-latency-comparison__row metrics-latency-comparison__row--accent">
                    <span>P95 E2E</span>
                    <span className="mono">{fmtMs(metrics.p95_latency_ms)}</span>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* ── Cost & usage ─────────────────────────────────────── */}
          <section className="metrics-section" aria-label="Cost and usage">
            <div className="metrics-section-header">
              <h2 className="metrics-section-title">Cost &amp; Usage</h2>
            </div>
            <div className="metrics-cost-grid">
              <StatCard
                icon={DollarSign}
                label="Total LLM Cost"
                value={llmCost.display}
                tooltip={llmCost.full}
                sub="Groq + OpenRouter"
                accent
              />
              <StatCard
                icon={Hash}
                label="Embedding Cost"
                value={embedCost.display}
                tooltip={embedCost.full}
                sub="NVIDIA / OpenRouter"
              />
              <StatCard
                icon={TrendingUp}
                label="Total Cost"
                value={totalCost.display}
                tooltip={totalCost.full}
                sub="Embedding + LLM"
              />
              <StatCard
                icon={BarChart3}
                label="Total Tokens"
                rawValue={metrics.total_tokens}
                value={metrics.total_tokens?.toLocaleString()}
                sub="Input + output"
              />
              {metrics.total_ade_credits != null && (
                <StatCard
                  icon={Zap}
                  label="ADE Credits Used"
                  value={fmt(metrics.total_ade_credits, 2)}
                  sub={`${metrics.ingestion_count ?? 0} ingestion(s)`}
                />
              )}
            </div>
          </section>

          {/* ── Recent queries ───────────────────────────────────── */}
          <section className="metrics-section metrics-section--table" aria-label="Recent queries">
            <div className="metrics-section-header">
              <h2 className="metrics-section-title">Recent Queries</h2>
              {showTimeTabs && (
                <div className="metrics-time-tabs" role="tablist" aria-label="Time range">
                  {TIME_TABS.map((tab) => (
                    <button
                      key={tab.id}
                      className={`metrics-time-tab ${timeTab === tab.id ? 'metrics-time-tab--active' : ''}`}
                      onClick={() => setTimeTab(tab.id)}
                      role="tab"
                      aria-selected={timeTab === tab.id}
                      id={`metrics-tab-${tab.id}`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <QueriesTable records={filteredRecords} navigate={navigate} />
          </section>
        </motion.div>
      )}

      {/* ── Empty state (no error, no loading, no data) ──────────── */}
      {!loading && !error && !metrics && (
        <div className="metrics-empty">
          <BarChart3 size={48} opacity={0.3} />
          <h3>No metrics yet</h3>
          <p>Start making queries to see pipeline telemetry here.</p>
          <button
            className="btn btn-primary"
            onClick={() => navigate('/query')}
            id="metrics-go-query-btn"
          >
            Go to Query
          </button>
        </div>
      )}
    </div>
  );
}
