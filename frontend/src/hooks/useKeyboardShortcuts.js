/**
 * useKeyboardShortcuts — D2-T4
 * Global keyboard shortcuts:
 *   Ctrl/Cmd+K → command palette
 *   G D → /documents
 *   G Q → /query
 *   G M → /metrics
 *   G E → /evaluation
 *   / → focus query input
 *   ? → shortcuts cheat sheet
 */

import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

export function useKeyboardShortcuts({ onOpenPalette, onOpenShortcuts }) {
  const navigate = useNavigate();
  const seqRef = useRef('');
  const seqTimer = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      // Skip if focus is in an input/textarea/select/[contenteditable]
      const tag = document.activeElement?.tagName;
      const editable = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
        || document.activeElement?.getAttribute('contenteditable') === 'true';

      // Ctrl/Cmd+K → command palette (always)
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        onOpenPalette?.();
        return;
      }

      if (editable) return;

      // ? → shortcuts modal
      if (e.key === '?') {
        e.preventDefault();
        onOpenShortcuts?.();
        return;
      }

      // / → focus query input
      if (e.key === '/') {
        e.preventDefault();
        const qi = document.getElementById('query-input');
        if (qi) { navigate('/query'); setTimeout(() => qi?.focus(), 300); }
        return;
      }

      // Sequence shortcuts: G D, G Q, G M, G E
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        seqRef.current += e.key.toLowerCase();
        clearTimeout(seqTimer.current);
        seqTimer.current = setTimeout(() => { seqRef.current = ''; }, 800);

        const seq = seqRef.current;
        if (seq === 'gd') { navigate('/'); seqRef.current = ''; }
        else if (seq === 'gq') { navigate('/query'); seqRef.current = ''; }
        else if (seq === 'gm') { navigate('/metrics'); seqRef.current = ''; }
        else if (seq === 'ge') { navigate('/evaluation'); seqRef.current = ''; }
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [navigate, onOpenPalette, onOpenShortcuts]);
}
