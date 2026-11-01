/**
 * StatCard — icon, label, big mono value, delta/subtext, optional sparkline
 */
import { useEffect, useState } from 'react';
import './charts.css';

function useCountUp(target, duration = 800) {
  const [value, setValue] = useState(0);
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  useEffect(() => {
    if (reduced || target == null || isNaN(Number(target))) {
      setValue(target);
      return;
    }
    const num = Number(target);
    const start = Date.now();
    const tick = () => {
      const elapsed = Date.now() - start;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(eased < 1 ? Math.round(eased * num) : num);
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [target, duration, reduced]);

  return value;
}

export function StatCard({
  icon: Icon,
  label,
  value,
  rawValue,         // numeric value for count-up animation
  sub,
  delta,            // { value: string, dir: 'up'|'down'|'same' }
  accent = false,
  className = '',
  sparklineData,    // optional array of numbers
  tooltip,
}) {
  const animated = useCountUp(rawValue != null ? rawValue : null);
  const displayValue = rawValue != null ? animated : value;

  return (
    <div className={`stat-card ${accent ? 'stat-card--accent' : ''} ${className}`}>
      {Icon && (
        <div className="stat-card__icon" aria-hidden="true">
          <Icon size={18} />
        </div>
      )}
      <div className="stat-card__body">
        <div
          className="stat-card__value mono"
          aria-label={label}
          title={tooltip || (typeof displayValue === 'string' ? displayValue : undefined)}
        >
          {displayValue}
        </div>
        <div className="stat-card__label">{label}</div>
        {sub && <div className="stat-card__sub">{sub}</div>}
        {delta && (
          <span
            className={`stat-card__delta stat-card__delta--${delta.dir}`}
            aria-label={`Change: ${delta.value}`}
          >
            {delta.dir === 'up' ? '▲' : delta.dir === 'down' ? '▼' : '—'} {delta.value}
          </span>
        )}
      </div>
      {sparklineData && (
        <div className="stat-card__sparkline" aria-hidden="true">
          <MiniSparkline data={sparklineData} />
        </div>
      )}
    </div>
  );
}

function MiniSparkline({ data }) {
  if (!data?.length) return null;
  const w = 80, h = 32;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x},${y}`;
  });
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} preserveAspectRatio="none">
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity="0.7"
      />
    </svg>
  );
}
