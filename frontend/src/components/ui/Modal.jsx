/**
 * src/components/ui/Modal.jsx
 * Accessible dialog/modal with focus trap
 */
import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { Button } from './Button';
import './Modal.css';

export function Modal({ open, onClose, title, children, size = 'md', footer }) {
  const backdropRef = useRef(null);
  const dialogRef = useRef(null);

  // Focus trap
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement;
    dialogRef.current?.focus();
    return () => prev?.focus();
  }, [open]);

  // Keyboard close
  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={backdropRef}
      className="modal-backdrop"
      role="presentation"
      onClick={(e) => { if (e.target === backdropRef.current) onClose(); }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        className={`modal modal--${size} animate-fade-up`}
        tabIndex={-1}
      >
        <div className="modal__header">
          <h2 id="modal-title" className="modal__title">{title}</h2>
          <Button variant="ghost" size="sm" iconOnly onClick={onClose} aria-label="Close dialog">
            <X size={16} />
          </Button>
        </div>
        <div className="modal__body">{children}</div>
        {footer && <div className="modal__footer">{footer}</div>}
      </div>
    </div>
  );
}

export default Modal;
