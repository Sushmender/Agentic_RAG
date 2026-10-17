/**
 * StageBar — horizontal bar with label, value, optional color
 * ComparisonBars — before vs after side-by-side bars
 * Sparkline — tiny inline line chart
 */
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer } from 'recharts';
import './charts.css';

/* ── StageBar ─────────────────────────────────────────────────────────────── */
export function StageBar({ label, value, displayValue, maxValue = 100, color = 'var(--accent)', note }) {
  const pct = maxValue > 0 ? Math.min((value / maxValue) * 100, 100) : 0;

  return (
    <div className="stage-bar">
      <div className="stage-bar__header">
        <span className="stage-bar__label">{label}</span>
        <span className="stage-bar__value mono">{displayValue ?? value}</span>
      </div>
      <div className="stage-bar__track" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div
          className="stage-bar__fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      {note && <div className="stage-bar__note">{note}</div>}
    </div>
  );
}

/* ── ComparisonBars ───────────────────────────────────────────────────────── */
export function ComparisonBars({ data, height = 180, className = '' }) {
  // data: [{ label, before, after }]
  if (!data?.length) return null;
  const chartData = data.map((d) => ({
    name: d.label,
    Before: typeof d.before === 'number' ? +(d.before * 100).toFixed(1) : 0,
    After: typeof d.after === 'number' ? +(d.after * 100).toFixed(1) : 0,
  }));

  return (
    <div className={`comparison-bars ${className}`} style={{ width: '100%', height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} barGap={4} barCategoryGap="25%">
          <XAxis
            dataKey="name"
            tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              fontSize: '12px',
            }}
            formatter={(v) => [`${v}%`]}
          />
          <Bar
            dataKey="Before"
            fill="var(--accent-2)"
            radius={[4, 4, 0, 0]}
            isAnimationActive={!window.matchMedia('(prefers-reduced-motion: reduce)').matches}
            animationDuration={600}
          />
          <Bar
            dataKey="After"
            fill="var(--accent)"
            radius={[4, 4, 0, 0]}
            isAnimationActive={!window.matchMedia('(prefers-reduced-motion: reduce)').matches}
            animationDuration={800}
          />
        </BarChart>
      </ResponsiveContainer>
      {/* Legend */}
      <div className="comparison-bars__legend">
        <span><span className="comparison-bars__dot" style={{ background: 'var(--accent-2)' }} /> Before</span>
        <span><span className="comparison-bars__dot" style={{ background: 'var(--accent)' }} /> After</span>
      </div>
    </div>
  );
}

/* ── Sparkline ────────────────────────────────────────────────────────────── */
export function Sparkline({ data, color = 'var(--accent)', height = 40, width = 120 }) {
  if (!data?.length) return null;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  });
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} preserveAspectRatio="none">
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
