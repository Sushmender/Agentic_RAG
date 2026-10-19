/**
 * frontend/src/components/chat/ChatTabStrip.jsx
 * Chrome-style tab strip for persistent multi-chat sessions.
 * Features:
 *   - Drag-to-reorder via framer-motion (default tab pinned first)
 *   - Roving tabindex + a11y (role=tablist, role=tab, Arrow keys, Home, End, Delete, F2)
 *   - Inline renaming on double-click or F2 (Enter saves, Esc cancels)
 *   - Middle-click to close (with undo toast for tabs with messages)
 *   - Pending spinner & unread accent dot
 *   - Auto-scroll active tab into view + edge fade masks
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { Reorder, useReducedMotion } from 'framer-motion';
import { MessageCircle, Plus, X, Loader2 } from 'lucide-react';
import { useChat } from '../../context/ChatContext';
import { Tooltip } from '../ui/Tooltip';
import './ChatTabStrip.css';

export function ChatTabStrip() {
  const {
    tabs,
    activeTabId,
    setActive,
    newTab,
    closeTab,
    renameTab,
    reorderTabs,
  } = useChat();

  const shouldReduceMotion = useReducedMotion();
  const scrollContainerRef = useRef(null);
  const activeTabRef = useRef(null);
  const tabButtonRefs = useRef({});

  const [editingTabId, setEditingTabId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [scrollState, setScrollState] = useState({ canLeft: false, canRight: false });

  // Update edge fade masks on scroll / resize
  const updateScrollState = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const canLeft = el.scrollLeft > 4;
    const canRight = el.scrollLeft + el.clientWidth < el.scrollWidth - 4;
    setScrollState((prev) => {
      if (prev.canLeft === canLeft && prev.canRight === canRight) return prev;
      return { canLeft, canRight };
    });
  }, []);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    updateScrollState();
    el.addEventListener('scroll', updateScrollState, { passive: true });
    window.addEventListener('resize', updateScrollState);
    return () => {
      el.removeEventListener('scroll', updateScrollState);
      window.removeEventListener('resize', updateScrollState);
    };
  }, [tabs, updateScrollState]);

  // Scroll active tab into view smoothly
  useEffect(() => {
    if (activeTabRef.current) {
      activeTabRef.current.scrollIntoView({
        behavior: shouldReduceMotion ? 'auto' : 'smooth',
        inline: 'nearest',
        block: 'nearest',
      });
    }
  }, [activeTabId, shouldReduceMotion]);

  // Start renaming
  const startRename = (tab) => {
    setEditingTabId(tab.id);
    setEditTitle(tab.title);
  };

  const commitRename = (tabId) => {
    if (editTitle.trim()) {
      renameTab(tabId, editTitle.trim());
    }
    setEditingTabId(null);
  };

  // Listen for global rename command/event
  useEffect(() => {
    const handler = (e) => {
      const tabId = e.detail?.tabId || activeTabId;
      const tab = tabs.find((t) => t.id === tabId);
      if (tab) startRename(tab);
    };
    window.addEventListener('chat:start-rename', handler);
    return () => window.removeEventListener('chat:start-rename', handler);
  }, [tabs, activeTabId]);

  const cancelRename = () => {
    setEditingTabId(null);
  };

  const handleCreateNew = () => {
    const created = newTab();
    if (created) {
      setTimeout(() => {
        document.getElementById('query-input')?.focus();
      }, 50);
    }
  };

  // Roving tabindex and keyboard navigation
  const handleKeyDown = (e, tab, index) => {
    if (editingTabId === tab.id) return;

    if (e.key === 'ArrowRight') {
      e.preventDefault();
      const nextIdx = (index + 1) % tabs.length;
      const nextTab = tabs[nextIdx];
      setActive(nextTab.id);
      tabButtonRefs.current[nextTab.id]?.focus();
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      const prevIdx = (index - 1 + tabs.length) % tabs.length;
      const prevTab = tabs[prevIdx];
      setActive(prevTab.id);
      tabButtonRefs.current[prevTab.id]?.focus();
    } else if (e.key === 'Home') {
      e.preventDefault();
      const firstTab = tabs[0];
      if (firstTab) {
        setActive(firstTab.id);
        tabButtonRefs.current[firstTab.id]?.focus();
      }
    } else if (e.key === 'End') {
      e.preventDefault();
      const lastTab = tabs[tabs.length - 1];
      if (lastTab) {
        setActive(lastTab.id);
        tabButtonRefs.current[lastTab.id]?.focus();
      }
    } else if (e.key === 'Delete') {
      if (tab.id !== 'default') {
        e.preventDefault();
        closeTab(tab.id);
      }
    } else if (e.key === 'F2') {
      e.preventDefault();
      startRename(tab);
    }
  };

  const maskClass =
    scrollState.canLeft && scrollState.canRight
      ? 'tab-strip--mask-both'
      : scrollState.canLeft
      ? 'tab-strip--mask-left'
      : scrollState.canRight
      ? 'tab-strip--mask-right'
      : '';

  return (
    <div className={`chat-tab-strip ${maskClass}`} role="region" aria-label="Chat tabs navigation">
      <div className="chat-tab-strip__scroll" ref={scrollContainerRef}>
        <Reorder.Group
          axis="x"
          values={tabs}
          onReorder={reorderTabs}
          className="chat-tab-strip__list"
          role="tablist"
          aria-label="Open chats"
        >
          {tabs.map((tab, index) => {
            const isActive = tab.id === activeTabId;
            const isEditing = editingTabId === tab.id;
            const isPending = tab.messages.some((m) => m.pending);
            const isDefault = tab.id === 'default';

            return (
              <Reorder.Item
                key={tab.id}
                value={tab}
                dragListener={!isDefault && !isEditing}
                className={`chat-tab-item ${isActive ? 'chat-tab-item--active' : ''} ${
                  isDefault ? 'chat-tab-item--default' : ''
                }`}
                ref={isActive ? activeTabRef : null}
                initial={shouldReduceMotion ? false : { opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={shouldReduceMotion ? false : { opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.15 }}
                layout={!shouldReduceMotion}
                onAuxClick={(e) => {
                  if (e.button === 1 && !isDefault) {
                    e.preventDefault();
                    e.stopPropagation();
                    closeTab(tab.id);
                  }
                }}
              >
                <div
                  ref={(el) => (tabButtonRefs.current[tab.id] = el)}
                  role="tab"
                  id={`tab-${tab.id}`}
                  aria-controls={`tabpanel-${tab.id}`}
                  aria-selected={isActive}
                  tabIndex={isActive ? 0 : -1}
                  className="chat-tab-item__btn"
                  onClick={() => {
                    if (!isEditing) setActive(tab.id);
                  }}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    startRename(tab);
                  }}
                  onKeyDown={(e) => handleKeyDown(e, tab, index)}
                >
                  {/* Icon slot: Pending spinner | Unread dot | Lucide MessageCircle */}
                  <div className="chat-tab-item__icon-slot" aria-hidden="true">
                    {isPending ? (
                      <Loader2 size={13} className="chat-tab-item__spinner animate-spin" />
                    ) : tab.hasUnread ? (
                      <span
                        className="chat-tab-item__unread-dot"
                        title="New answer received"
                        aria-label="Unread answer"
                      />
                    ) : (
                      <MessageCircle
                        size={13}
                        className="chat-tab-item__icon"
                        strokeWidth={isActive ? 2.2 : 1.8}
                      />
                    )}
                  </div>

                  {/* Title or inline edit input */}
                  {isEditing ? (
                    <input
                      type="text"
                      className="chat-tab-item__rename-input"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => {
                        e.stopPropagation();
                        if (e.key === 'Enter') commitRename(tab.id);
                        if (e.key === 'Escape') cancelRename();
                      }}
                      onBlur={() => commitRename(tab.id)}
                      autoFocus
                      onClick={(e) => e.stopPropagation()}
                      maxLength={60}
                      aria-label="Rename chat"
                    />
                  ) : (
                    <Tooltip content={tab.title} placement="top">
                      <span className="chat-tab-item__title">{tab.title}</span>
                    </Tooltip>
                  )}

                  {/* Close button (pinned inside tab padding at far right) or spacer for default tab */}
                  {isDefault ? (
                    <span className="chat-tab-item__close-spacer" aria-hidden="true" />
                  ) : (
                    <button
                      type="button"
                      className="chat-tab-item__close"
                      onClick={(e) => {
                        e.stopPropagation();
                        closeTab(tab.id);
                      }}
                      aria-label={`Close chat ${tab.title}`}
                      tabIndex={-1}
                    >
                      <X size={12} />
                    </button>
                  )}
                </div>
              </Reorder.Item>
            );
          })}
        </Reorder.Group>
      </div>

      {/* Pinned "+" button at right */}
      <div className="chat-tab-strip__actions">
        <Tooltip content="New chat" placement="top">
          <button
            type="button"
            className="chat-tab-strip__add-btn"
            onClick={handleCreateNew}
            aria-label="Open new chat"
          >
            <Plus size={15} />
          </button>
        </Tooltip>
      </div>
    </div>
  );
}
