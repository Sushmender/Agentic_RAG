/**
 * CommandPalette.jsx — D2-T4
 * Ctrl/Cmd+K opens a command palette powered by cmdk.
 * Commands: navigate to pages, switch model, logout, start new query.
 */

import { useEffect, useState, useCallback } from 'react';
import { Command } from 'cmdk';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText, MessageSquare, BarChart3, FlaskConical,
  LogOut, Plus, Search, X, ArrowRight, ArrowLeft, Edit3,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useChat } from '../../context/ChatContext';
import './CommandPalette.css';

const BASE_COMMANDS = [
  {
    group: 'Navigate',
    items: [
      { id: 'go-documents', label: 'Go to Documents', icon: FileText, shortcut: 'G D', action: (nav) => nav('/') },
      { id: 'go-query',     label: 'Go to Query',     icon: MessageSquare, shortcut: 'G Q', action: (nav) => nav('/query') },
      { id: 'go-metrics',   label: 'Go to Metrics',   icon: BarChart3, shortcut: 'G M', action: (nav) => nav('/metrics') },
      { id: 'go-eval',      label: 'Go to Evaluation',icon: FlaskConical, shortcut: 'G E', action: (nav) => nav('/evaluation') },
    ],
  },
  {
    group: 'Chat Tabs',
    items: [
      {
        id: 'new-chat',
        label: 'New chat',
        icon: Plus,
        shortcut: 'Alt N',
        action: (nav, logout, chat) => {
          chat.newTab();
          nav('/query');
          setTimeout(() => document.getElementById('query-input')?.focus(), 50);
        },
      },
      {
        id: 'close-chat',
        label: 'Close chat',
        icon: X,
        shortcut: 'Alt W',
        action: (nav, logout, chat) => {
          if (chat.activeTabId !== 'default') {
            chat.closeTab(chat.activeTabId);
          }
        },
      },
      {
        id: 'next-chat',
        label: 'Next chat',
        icon: ArrowRight,
        shortcut: 'Alt →',
        action: (nav, logout, chat) => {
          const idx = chat.tabs.findIndex((t) => t.id === chat.activeTabId);
          const nextIdx = (idx + 1) % chat.tabs.length;
          chat.setActive(chat.tabs[nextIdx].id);
          nav('/query');
        },
      },
      {
        id: 'prev-chat',
        label: 'Previous chat',
        icon: ArrowLeft,
        shortcut: 'Alt ←',
        action: (nav, logout, chat) => {
          const idx = chat.tabs.findIndex((t) => t.id === chat.activeTabId);
          const prevIdx = (idx - 1 + chat.tabs.length) % chat.tabs.length;
          chat.setActive(chat.tabs[prevIdx].id);
          nav('/query');
        },
      },
      {
        id: 'rename-chat',
        label: 'Rename chat',
        icon: Edit3,
        shortcut: 'F2',
        action: (nav, logout, chat) => {
          nav('/query');
          setTimeout(() => {
            window.dispatchEvent(
              new CustomEvent('chat:start-rename', {
                detail: { tabId: chat.activeTabId },
              })
            );
          }, 50);
        },
      },
    ],
  },
  {
    group: 'Actions',
    items: [
      { id: 'new-query', label: 'New Query', icon: Plus, action: (nav) => { nav('/query'); setTimeout(() => document.getElementById('query-input')?.focus(), 300); } },
      { id: 'logout',    label: 'Sign out',  icon: LogOut, danger: true, action: (nav, logout) => { logout(); nav('/login'); } },
    ],
  },
];

export function CommandPalette({ open, onClose }) {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const chat = useChat();
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (!open) setSearch('');
  }, [open]);

  const runCommand = useCallback((action) => {
    action(navigate, logout, chat);
    onClose();
  }, [navigate, logout, chat, onClose]);

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement;
    const handler = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => {
      document.removeEventListener('keydown', handler);
      prev?.focus?.();
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="cmd-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onClick={onClose}
          role="dialog"
          aria-modal="true"
          aria-label="Command palette"
        >
          <motion.div
            className="cmd-dialog"
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -12 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            onClick={(e) => e.stopPropagation()}
          >
            <Command shouldFilter={true} loop>
              <div className="cmd-input-wrap">
                <Search size={16} className="cmd-search-icon" />
                <Command.Input
                  className="cmd-input"
                  placeholder="Search commands…"
                  value={search}
                  onValueChange={setSearch}
                  autoFocus
                  aria-label="Command search"
                />
                <kbd className="cmd-esc-hint">ESC</kbd>
              </div>

              <Command.List className="cmd-list">
                <Command.Empty className="cmd-empty">
                  No commands found for "{search}"
                </Command.Empty>

                {BASE_COMMANDS.map((group) => (
                  <Command.Group key={group.group} heading={group.group} className="cmd-group">
                    {group.items.map((item) => (
                      <Command.Item
                        key={item.id}
                        value={item.label}
                        className={`cmd-item ${item.danger ? 'cmd-item--danger' : ''}`}
                        onSelect={() => runCommand(item.action)}
                        id={`cmd-${item.id}`}
                      >
                        <item.icon size={15} className="cmd-item__icon" />
                        <span className="cmd-item__label">{item.label}</span>
                        {item.shortcut && (
                          <span className="cmd-item__shortcut">
                            {item.shortcut.split(' ').map((k, i) => (
                              <kbd key={i} className="cmd-kbd">{k}</kbd>
                            ))}
                          </span>
                        )}
                      </Command.Item>
                    ))}
                  </Command.Group>
                ))}
              </Command.List>

              <div className="cmd-footer">
                <span><kbd className="cmd-kbd">↑↓</kbd> navigate</span>
                <span><kbd className="cmd-kbd">↵</kbd> select</span>
                <span><kbd className="cmd-kbd">ESC</kbd> close</span>
              </div>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
