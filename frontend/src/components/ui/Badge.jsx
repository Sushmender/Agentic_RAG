/**
 * src/components/ui/Badge.jsx
 * Badge / Chip with semantic variants
 */
import './Badge.css';

const VARIANT_MAP = {
  success: 'badge-success',
  warn:    'badge-warn',
  danger:  'badge-danger',
  info:    'badge-info',
  neutral: 'badge-neutral',
  accent2: 'badge-accent2',
  // status aliases
  pending:    'badge-neutral',
  processing: 'badge-warn',
  completed:  'badge-success',
  failed:     'badge-danger',
  cached:     'badge-info',
};

export function Badge({ variant = 'neutral', dot = false, children, className = '' }) {
  const variantClass = VARIANT_MAP[variant] || 'badge-neutral';
  return (
    <span className={`badge ${variantClass} ${className}`}>
      {dot && <span className="badge__dot" aria-hidden="true" />}
      {children}
    </span>
  );
}

export function StatusBadge({ status }) {
  const labels = {
    pending:    'Pending',
    processing: 'Processing',
    completed:  'Complete',
    failed:     'Failed',
  };
  return <Badge variant={status} dot>{labels[status] || status}</Badge>;
}

export default Badge;
