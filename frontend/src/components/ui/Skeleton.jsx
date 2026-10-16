/**
 * src/components/ui/Skeleton.jsx
 * Skeleton loading placeholder
 */
import './Skeleton.css';

export function Skeleton({ width, height, className = '', variant = 'rect' }) {
  return (
    <span
      className={`skel skel--${variant} skeleton ${className}`}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

export function SkeletonText({ lines = 3, className = '' }) {
  return (
    <div className={`skel-text ${className}`}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton
          key={i}
          variant="text"
          width={i === lines - 1 ? '60%' : '100%'}
        />
      ))}
    </div>
  );
}

export default Skeleton;
