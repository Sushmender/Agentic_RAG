/**
 * ShortcutsModal — ? key opens keyboard shortcut cheat sheet
 */
import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Keyboard } from 'lucide-react';
import './ShortcutsModal.css';

const SHORTCUTS = [
  {
    group: 'Navigation',
    items: [
      { keys: ['G', 'D'], label: 'Documents page' },
      { keys: ['G', 'Q'], label: 'Query page' },
      { keys: ['G', 'M'], label: 'Metrics page' },
      { keys: ['G', 'E'], label: 'Evaluation page' },
    ],
  },
  {
    group: 'Actions',
    items: [
      { keys: ['Ctrl', 'K'], label: 'Open command palette' },
      { keys: ['/'], label: 'Focus query input' },
      { keys: ['?'], label: 'Show keyboard shortcuts' },
      { keys: ['Ctrl', '↵'], label: 'Submit query' },
    ],
  },
  {
    group: 'Dialogs',
    items: [
      { keys: ['ESC'], label: 'Close dialog / modal' },
    ],
  },
];

export function ShortcutsModal({ open, onClose }) {
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement;
    const h = (e) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', h);
    return () => {
      document.removeEventListener('keydown', h);
      prev?.focus?.();
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="shortcuts-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          role="dialog"
          aria-modal="true"
          aria-label="Keyboard shortcuts"
        >
          <motion.div
            className="shortcuts-dialog"
            initial={{ opacity: 0, scale: 0.95, y: -12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="shortcuts-header">
              <div className="shortcuts-header-left">
                <Keyboard size={16} />
                <span>Keyboard Shortcuts</span>
              </div>
              <button
                className="shortcuts-close"
                onClick={onClose}
                aria-label="Close shortcuts"
              >
                <X size={16} />
              </button>
            </div>

            <div className="shortcuts-body">
              {SHORTCUTS.map((group) => (
                <div key={group.group} className="shortcuts-group">
                  <div className="shortcuts-group-title">{group.group}</div>
                  {group.items.map((item) => (
                    <div key={item.label} className="shortcuts-row">
                      <span className="shortcuts-label">{item.label}</span>
                      <span className="shortcuts-keys">
                        {item.keys.map((k, i) => (
                          <span key={i}>
                            <kbd className="shortcuts-kbd">{k}</kbd>
                            {i < item.keys.length - 1 && (
                              <span className="shortcuts-plus">+</span>
                            )}
                          </span>
                        ))}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
