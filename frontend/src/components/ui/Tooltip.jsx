/**
 * src/components/ui/Tooltip.jsx
 * Simple CSS tooltip wrapper
 */
import './Tooltip.css';

export function Tooltip({ content, placement = 'top', children }) {
  return (
    <span className={`tooltip-wrap tooltip-wrap--${placement}`} data-tip={content}>
      {children}
    </span>
  );
}

export default Tooltip;
