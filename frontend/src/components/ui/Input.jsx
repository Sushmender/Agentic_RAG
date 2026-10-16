/**
 * src/components/ui/Input.jsx
 * Input, Textarea, Select, PasswordInput primitives
 */
import { useState, forwardRef } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import './Input.css';

export const Input = forwardRef(function Input(
  { label, error, hint, className = '', ...props },
  ref
) {
  return (
    <div className={`field ${className}`}>
      {label && <label className="field__label">{label}</label>}
      <input ref={ref} className={`field__input ${error ? 'field__input--error' : ''}`} {...props} />
      {error && <span className="field__error" role="alert">{error}</span>}
      {hint && !error && <span className="field__hint">{hint}</span>}
    </div>
  );
});

export const Textarea = forwardRef(function Textarea(
  { label, error, hint, className = '', ...props },
  ref
) {
  return (
    <div className={`field ${className}`}>
      {label && <label className="field__label">{label}</label>}
      <textarea ref={ref} className={`field__input field__textarea ${error ? 'field__input--error' : ''}`} {...props} />
      {error && <span className="field__error" role="alert">{error}</span>}
      {hint && !error && <span className="field__hint">{hint}</span>}
    </div>
  );
});

export const Select = forwardRef(function Select(
  { label, error, children, className = '', ...props },
  ref
) {
  return (
    <div className={`field ${className}`}>
      {label && <label className="field__label">{label}</label>}
      <select ref={ref} className={`field__input field__select ${error ? 'field__input--error' : ''}`} {...props}>
        {children}
      </select>
      {error && <span className="field__error" role="alert">{error}</span>}
    </div>
  );
});

export const PasswordInput = forwardRef(function PasswordInput(
  { label, error, hint, className = '', ...props },
  ref
) {
  const [show, setShow] = useState(false);
  return (
    <div className={`field ${className}`}>
      {label && <label className="field__label">{label}</label>}
      <div className="field__password-wrapper">
        <input
          ref={ref}
          type={show ? 'text' : 'password'}
          className={`field__input field__input--password ${error ? 'field__input--error' : ''}`}
          {...props}
        />
        <button
          type="button"
          className="field__password-toggle"
          onClick={() => setShow(v => !v)}
          aria-label={show ? 'Hide password' : 'Show password'}
        >
          {show ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
      {error && <span className="field__error" role="alert">{error}</span>}
      {hint && !error && <span className="field__hint">{hint}</span>}
    </div>
  );
});
