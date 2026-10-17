/**
 * RingChart — pure SVG donut with center label
 * P-3: Full track circle in --bg-elevated, progress arc in accent, round caps,
 * animated stroke-dashoffset, center label as HTML overlay with no background or border.
 */
import { useEffect, useState } from 'react';
import './charts.css';

export function RingChart({
  percent,             // 0 to 100
  segments,            // optional [{ value, color }] fallback for compatibility
  centerLabel,         // main text in center (e.g. "25.0%")
  centerSub,           // sub-text in center (e.g. "hit rate")
  size = 130,
  strokeWidth = 10,
  className = '',
}) {
  const [animatedPct, setAnimatedPct] = useState(0);

  // Derive percentage from prop or segments
  const pct = percent != null && !isNaN(percent)
    ? Number(percent)
    : segments?.[0]?.value != null
      ? Number(segments[0].value)
      : 0;

  const validPct = Math.max(0, Math.min(100, pct));

  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      setAnimatedPct(validPct);
      return;
    }
    const timer = setTimeout(() => {
      setAnimatedPct(validPct);
    }, 50);
    return () => clearTimeout(timer);
  }, [validPct]);

  // SVG circle calculations
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const strokeDashoffset = c - (animatedPct / 100) * c;

  return (
    <div
      className={`ring-chart ${className}`}
      style={{ width: size, height: size, position: 'relative' }}
      role="img"
      aria-label={`Cache hit rate: ${centerLabel ?? `${validPct}%`}`}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="ring-chart__svg"
      >
        {/* Track circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--bg-elevated)"
          strokeWidth={strokeWidth}
        />
        {/* Progress arc */}
        {validPct > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={strokeWidth}
            strokeDasharray={c}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            className="ring-chart__progress"
          />
        )}
      </svg>
      {/* Center label HTML overlay with no background or border */}
      <div className="ring-chart__center">
        <span className="ring-chart__main mono">{centerLabel ?? `${validPct.toFixed(1)}%`}</span>
        {centerSub && <span className="ring-chart__sub">{centerSub}</span>}
      </div>
    </div>
  );
}
