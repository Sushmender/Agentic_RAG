/**
 * src/components/layout/AppShell.jsx
 * Dark IDE-style app shell:
 *   - 72px icon rail on the left
 *   - 52px top bar (title + breadcrumb, status chips, avatar menu)
 *   - Main content outlet
 *   - 36px bottom status bar
 * Responsive: <900px → bottom tab bar; <640px → status bar hides
 * D2-T4: Command palette (Ctrl/Cmd+K), keyboard shortcuts, shortcuts modal
 */

import { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate, Outlet } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText,
  MessageSquare,
  BarChart3,
  FlaskConical,
  LogOut,
  User,
  Activity,
  ChevronDown,
  Wifi,
  WifiOff,
  Command,
} from 'lucide-react';
import { Tooltip } from '../ui/Tooltip';
import { useAuth } from '../../context/AuthContext';
import { healthAPI } from '../../services/api';
import { CommandPalette } from './CommandPalette';
import { ShortcutsModal } from './ShortcutsModal';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import './AppShell.css';

const NAV_ITEMS = [
  { path: '/',           label: 'Documents', icon: FileText,     id: 'nav-documents' },
  { path: '/query',      label: 'Query',     icon: MessageSquare, id: 'nav-query'     },
  { path: '/metrics',    label: 'Metrics',   icon: BarChart3,    id: 'nav-metrics'   },
  { path: '/evaluation', label: 'Evaluation',icon: FlaskConical, id: 'nav-evaluation'},
];

const PAGE_META = {
  '/':           { title: 'Documents',   sub: 'Upload & manage your files' },
  '/query':      { title: 'Query',       sub: 'Ask questions about your data' },
  '/metrics':    { title: 'Metrics',     sub: 'Pipeline observability' },
  '/evaluation': { title: 'Evaluation',  sub: 'Recall & precision benchmarks' },
};

export default function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [health, setHealth] = useState(null); // null = unknown, true = ok, false = down
  const [cmdOpen, setCmdOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  useKeyboardShortcuts({
    onOpenPalette: () => setCmdOpen(true),
    onOpenShortcuts: () => setShortcutsOpen(true),
  });

  const meta = PAGE_META[location.pathname] || { title: 'RAG', sub: '' };

  // Health poll every 30s
  const pollHealth = useCallback(async () => {
    try {
      await healthAPI.check();
      setHealth(prev => (prev === true ? prev : true));
    } catch {
      setHealth(prev => (prev === false ? prev : false));
    }
  }, []);

  useEffect(() => {
    pollHealth();
    const id = setInterval(pollHealth, 30_000);
    return () => clearInterval(id);
  }, [pollHealth]);

  const handleLogout = () => {
    setUserMenuOpen(false);
    logout();
    navigate('/login');
  };

  const isActive = (path) =>
    path === '/' ? location.pathname === '/' : location.pathname.startsWith(path);

  return (
    <div className="shell">
      {/* ── Left Icon Rail ─────────────────────────────────────── */}
      <nav className="rail" aria-label="Main navigation">
        {/* Logo */}
        <div className="rail__logo" aria-label="Multimodal RAG">
          <div className="rail__logo-mark" aria-hidden="true">
            <Activity size={20} />
          </div>
        </div>

        {/* Nav items */}
        <ul className="rail__items" role="list">
          {NAV_ITEMS.map(({ path, label, icon: Icon, id }) => {
            const active = isActive(path);
            return (
              <li key={path} className="rail__item-wrap">
                <Tooltip content={label} placement="right">
                  <button
                    id={id}
                    className={`rail__item ${active ? 'rail__item--active' : ''}`}
                    onClick={() => navigate(path)}
                    aria-label={label}
                    aria-current={active ? 'page' : undefined}
                  >
                    {active && (
                      <motion.span
                        layoutId="rail-indicator"
                        className="rail__indicator"
                        transition={{ type: 'spring', stiffness: 400, damping: 35 }}
                      />
                    )}
                    <Icon size={20} strokeWidth={active ? 2.5 : 1.8} />
                  </button>
                </Tooltip>
              </li>
            );
          })}
        </ul>

        {/* Bottom: user avatar */}
        <div className="rail__bottom">
          <div className="rail__avatar-wrap">
            <Tooltip content={`${user?.username} — Account`} placement="right">
              <button
                className="rail__avatar"
                onClick={() => setUserMenuOpen(v => !v)}
                aria-label="User menu"
                aria-expanded={userMenuOpen}
              >
                <User size={18} />
              </button>
            </Tooltip>
            <AnimatePresence>
              {userMenuOpen && (
                <motion.div
                  className="user-menu"
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -8 }}
                  transition={{ duration: 0.15 }}
                >
                  <div className="user-menu__header">
                    <span className="user-menu__name">{user?.username}</span>
                    <span className="user-menu__label">Signed in</span>
                  </div>
                  <hr className="user-menu__divider" />
                  <button
                    className="user-menu__item user-menu__item--danger"
                    onClick={handleLogout}
                    id="logout-btn"
                  >
                    <LogOut size={14} />
                    Sign out
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </nav>

      {/* ── Main area ──────────────────────────────────────────── */}
      <div className="shell__main">
        {/* Top bar */}
        <header className="topbar">
          <div className="topbar__left">
            <h1 className="topbar__title">{meta.title}</h1>
            {meta.sub && <span className="topbar__sub">{meta.sub}</span>}
          </div>
          <div className="topbar__chips">
            {health === true && (
              <span className="status-chip status-chip--ok" title="Backend reachable">
                <Wifi size={12} />
                Connected
              </span>
            )}
            {health === false && (
              <span className="status-chip status-chip--error" title="Backend unreachable">
                <WifiOff size={12} />
                Offline
              </span>
            )}
            <button
              className="topbar__cmd-hint"
              onClick={() => setCmdOpen(true)}
              aria-label="Open command palette"
              title="Command palette (Ctrl+K)"
            >
              <Command size={12} />
              <span>Ctrl K</span>
            </button>
          </div>
          <div className="topbar__right">
            <button
              className="topbar__avatar-btn"
              onClick={() => setUserMenuOpen(v => !v)}
              aria-label="User menu"
            >
              <span className="topbar__avatar-initial">
                {user?.username?.[0]?.toUpperCase()}
              </span>
              <span className="topbar__username">{user?.username}</span>
              <ChevronDown size={14} />
            </button>
          </div>
        </header>

        {/* Backend down banner */}
        <AnimatePresence>
          {health === false && (
            <motion.div
              className="offline-banner"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              role="alert"
            >
              <WifiOff size={14} />
              Backend is unreachable. Check that the server is running on port 8000.
              <button className="offline-banner__retry" onClick={pollHealth}>
                Retry
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Page outlet with route transition */}
        <main className="shell__content" id="main-content">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              className="shell__page"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>

        {/* Bottom status bar */}
        <footer className="statusbar" aria-label="Pipeline status">
          <div className="statusbar__left">
            <span className="statusbar__item">
              <span className="statusbar__dot" style={{ background: 'var(--accent)' }} />
              Multimodal RAG
            </span>
          </div>
          <div className="statusbar__right">
            <span className="statusbar__item">v0.1.0</span>
          </div>
        </footer>
      </div>

      {/* ── Bottom tab bar (mobile <900px) ─────────────────────── */}
      <nav className="bottom-tabs" aria-label="Mobile navigation">
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => {
          const active = isActive(path);
          return (
            <button
              key={path}
              className={`bottom-tab ${active ? 'bottom-tab--active' : ''}`}
              onClick={() => navigate(path)}
              aria-label={label}
              aria-current={active ? 'page' : undefined}
            >
              <Icon size={20} strokeWidth={active ? 2.5 : 1.8} />
              <span className="bottom-tab__label">{label}</span>
            </button>
          );
        })}
      </nav>

      {/* ── Command Palette ─────────────────────────────────────── */}
      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />

      {/* ── Shortcuts Modal ─────────────────────────────────────── */}
      <ShortcutsModal open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </div>
  );
}
