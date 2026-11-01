/**
 * src/components/ui/Button.jsx
 * Button primitive — variants: primary, secondary, ghost, danger, icon
 */
import { forwardRef } from 'react';
import './Button.css';

export const Button = forwardRef(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading = false,
    icon,
    iconOnly = false,
    children,
    className = '',
    disabled,
    ...props
  },
  ref
) {
  const cls = [
    'btn',
    `btn--${variant}`,
    `btn--${size}`,
    iconOnly && 'btn--icon-only',
    loading && 'btn--loading',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button ref={ref} className={cls} disabled={disabled || loading} {...props}>
      {loading ? (
        <span className="btn__spinner" aria-hidden="true" />
      ) : icon ? (
        <span className="btn__icon" aria-hidden="true">{icon}</span>
      ) : null}
      {!iconOnly && children && <span className="btn__label">{children}</span>}
      {iconOnly && <span className="sr-only">{children}</span>}
    </button>
  );
});

export default Button;
