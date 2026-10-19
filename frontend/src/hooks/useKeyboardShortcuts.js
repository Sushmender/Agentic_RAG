/**
 * useKeyboardShortcuts — D2-T4 + Chat tabs shortcuts
 * Global keyboard shortcuts:
 *   Ctrl/Cmd+K → command palette
 *   Alt+N → new chat tab
 *   Alt+W → close current chat tab
 *   Alt+1..9 → jump to chat tab N
 *   Alt+ArrowLeft/Right → switch chat tabs
 *   F2 → rename active chat tab
 *   G D → /documents
 *   G Q → /query
 *   G M → /metrics
 *   G E → /evaluation
 *   / → focus query input
 *   ? → shortcuts cheat sheet
 */

import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChat } from '../context/ChatContext';

export function useKeyboardShortcuts({ onOpenPalette, onOpenShortcuts }) {
  const navigate = useNavigate();
  const { tabs, activeTabId, setActive, newTab, closeTab } = useChat();
  const seqRef = useRef('');
  const seqTimer = useRef(null);

  const tabsRef = useRef(tabs);
  const activeTabIdRef = useRef(activeTabId);

  useEffect(() => {
    tabsRef.current = tabs;
    activeTabIdRef.current = activeTabId;
  }, [tabs, activeTabId]);

  useEffect(() => {
    const handler = (e) => {
      // Ctrl/Cmd+K → command palette (always)
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        onOpenPalette?.();
        return;
      }

      // Alt shortcuts (Tab management)
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        // Alt+N → new chat
        if (e.key === 'n' || e.key === 'N') {
          e.preventDefault();
          newTab();
          navigate('/query');
          setTimeout(() => document.getElementById('query-input')?.focus(), 50);
          return;
        }

        // Alt+W → close current chat (ignored on default tab)
        if (e.key === 'w' || e.key === 'W') {
          e.preventDefault();
          if (activeTabIdRef.current !== 'default') {
            closeTab(activeTabIdRef.current);
          }
          return;
        }

        // Alt+1..9 → jump to tab N (1-indexed)
        if (e.key >= '1' && e.key <= '9') {
          const tabIdx = parseInt(e.key, 10) - 1;
          const currentTabs = tabsRef.current;
          if (tabIdx < currentTabs.length) {
            e.preventDefault();
            setActive(currentTabs[tabIdx].id);
            navigate('/query');
            return;
          }
        }

        // Alt+ArrowRight → next tab
        if (e.key === 'ArrowRight') {
          e.preventDefault();
          const currentTabs = tabsRef.current;
          const idx = currentTabs.findIndex((t) => t.id === activeTabIdRef.current);
          const nextIdx = (idx + 1) % currentTabs.length;
          setActive(currentTabs[nextIdx].id);
          navigate('/query');
          return;
        }

        // Alt+ArrowLeft → prev tab
        if (e.key === 'ArrowLeft') {
          e.preventDefault();
          const currentTabs = tabsRef.current;
          const idx = currentTabs.findIndex((t) => t.id === activeTabIdRef.current);
          const prevIdx = (idx - 1 + currentTabs.length) % currentTabs.length;
          setActive(currentTabs[prevIdx].id);
          navigate('/query');
          return;
        }
      }

      // F2 → rename active chat tab
      if (e.key === 'F2') {
        e.preventDefault();
        window.dispatchEvent(
          new CustomEvent('chat:start-rename', {
            detail: { tabId: activeTabIdRef.current },
          })
        );
        return;
      }

      // Skip remaining if focus is in an input/textarea/select/[contenteditable]
      const tag = document.activeElement?.tagName;
      const editable =
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        document.activeElement?.getAttribute('contenteditable') === 'true';

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
        if (qi) {
          navigate('/query');
          setTimeout(() => qi?.focus(), 300);
        }
        return;
      }

      // Sequence shortcuts: G D, G Q, G M, G E
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        seqRef.current += e.key.toLowerCase();
        clearTimeout(seqTimer.current);
        seqTimer.current = setTimeout(() => {
          seqRef.current = '';
        }, 800);

        const seq = seqRef.current;
        if (seq === 'gd') {
          navigate('/');
          seqRef.current = '';
        } else if (seq === 'gq') {
          navigate('/query');
          seqRef.current = '';
        } else if (seq === 'gm') {
          navigate('/metrics');
          seqRef.current = '';
        } else if (seq === 'ge') {
          navigate('/evaluation');
          seqRef.current = '';
        }
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [navigate, newTab, closeTab, setActive, onOpenPalette, onOpenShortcuts]);
}
