/**
 * src/components/layout/UserMenu.jsx
 * Reusable user trigger & popover menu component.
 * Features:
 *  - Anchors to its own trigger via getBoundingClientRect & portal to document.body
 *  - Recomputes on resize and scroll, flips / shifts to prevent viewport clipping
 *  - Full keyboard navigation (ArrowUp/Down, Home, End, Escape, Enter, Space)
 *  - ARIA menu & menuitem semantics, returns focus to trigger on close
 *  - Supports both controlled and uncontrolled states; closes other menus on open
 */

import { useState, useRef, useEffect, useCallback, useId } from 'react';
import { createPortal } from 'react-dom';
import { useLocation } from 'react-router-dom';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import {
  Keyboard,
  Command,
  LogOut,
  User,
  ChevronDown,
} from 'lucide-react';
import { Tooltip } from '../ui/Tooltip';
import { Kbd } from '../ui/Kbd';
import './UserMenu.css';

export function UserMenu({
  placement = 'bottom-end',
  triggerVariant,
  isOpen: propIsOpen,
  onOpenChange,
  user,
  health,
  onOpenShortcuts,
  onOpenPalette,
  onLogout,
  id: customId,
  tooltipText,
}) {
  const generatedId = useId();
  const id = customId || generatedId;
  const location = useLocation();
  const shouldReduceMotion = useReducedMotion();

  // Variant: default to 'topbar' for bottom-end, 'rail' for right-end
  const variant = triggerVariant || (placement === 'right-end' ? 'rail' : 'topbar');

  // Controlled vs uncontrolled state
  const isControlled = propIsOpen !== undefined;
  const [internalOpen, setInternalOpen] = useState(false);
  const isOpen = isControlled ? propIsOpen : internalOpen;

  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const itemRefs = useRef([]);
  const wasOpenRef = useRef(false);
  const [focusedIndex, setFocusedIndex] = useState(0);

  const [coords, setCoords] = useState({ top: 0, left: 0, transformOrigin: 'top right' });

  // Update open state and broadcast to ensure only one menu is open at a time
  const setIsOpen = useCallback(
    (nextVal) => {
      const value = typeof nextVal === 'function' ? nextVal(isOpen) : nextVal;
      if (value) {
        // Broadcast open event to close any other UserMenu
        window.dispatchEvent(new CustomEvent('usermenu:open', { detail: { id } }));
      }
      if (isControlled) {
        onOpenChange?.(value);
      } else {
        setInternalOpen(value);
        onOpenChange?.(value);
      }
    },
    [id, isControlled, isOpen, onOpenChange]
  );

  // Close when another UserMenu opens
  useEffect(() => {
    const handleOtherOpen = (e) => {
      if (e.detail?.id !== id && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener('usermenu:open', handleOtherOpen);
    return () => window.removeEventListener('usermenu:open', handleOtherOpen);
  }, [id, isOpen, setIsOpen]);

  // Close on route change
  useEffect(() => {
    if (isOpen) {
      setIsOpen(false);
    }
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  // Position calculation
  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const triggerRect = triggerRef.current.getBoundingClientRect();
    const menuEl = menuRef.current;
    const menuWidth = menuEl ? menuEl.offsetWidth : 260;
    const menuHeight = menuEl ? menuEl.offsetHeight : 230;
    const gap = 8;
    const pad = 12; // Minimum padding from viewport boundary
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let top = 0;
    let left = 0;
    let origin = 'top right';

    if (placement === 'bottom-end') {
      // Preferred: directly below trigger, right-aligned to trigger
      top = triggerRect.bottom + gap;
      left = triggerRect.right - menuWidth;
      origin = 'top right';

      // Flip vertically if overflowing bottom
      if (top + menuHeight > vh - pad) {
        const topSpace = triggerRect.top - gap - menuHeight;
        if (topSpace >= pad) {
          top = topSpace;
          origin = 'bottom right';
        } else {
          top = Math.max(pad, vh - pad - menuHeight);
        }
      }

      // Shift horizontally to prevent overflow
      if (left + menuWidth > vw - pad) {
        left = vw - pad - menuWidth;
      }
      if (left < pad) {
        left = pad;
      }
    } else if (placement === 'right-end') {
      // Preferred: to the right of trigger, bottom-aligned with trigger
      left = triggerRect.right + gap;
      top = triggerRect.bottom - menuHeight;
      origin = 'bottom left';

      // Flip or clamp vertically
      if (top < pad) {
        top = pad;
        origin = 'top left';
      }
      if (top + menuHeight > vh - pad) {
        top = Math.max(pad, vh - pad - menuHeight);
      }

      // Flip or shift horizontally (e.g. mobile 390px)
      if (left + menuWidth > vw - pad) {
        const leftSpace = triggerRect.left - gap - menuWidth;
        if (leftSpace >= pad) {
          left = leftSpace;
          origin = 'bottom right';
        } else {
          left = Math.max(pad, vw - pad - menuWidth);
          origin = 'bottom center';
        }
      }
    } else {
      // Generic fallback
      top = triggerRect.bottom + gap;
      left = Math.max(pad, Math.min(triggerRect.left, vw - pad - menuWidth));
      origin = 'top left';
    }

    setCoords({
      top: Math.round(top),
      left: Math.round(left),
      transformOrigin: origin,
    });
  }, [placement]);

  // Recompute position on resize and scroll
  useEffect(() => {
    if (!isOpen) return;

    updatePosition();
    const handleScrollOrResize = () => updatePosition();

    window.addEventListener('resize', handleScrollOrResize);
    window.addEventListener('scroll', handleScrollOrResize, true);

    // Frame after render to adjust with measured dimensions
    const rafId = requestAnimationFrame(updatePosition);

    return () => {
      window.removeEventListener('resize', handleScrollOrResize);
      window.removeEventListener('scroll', handleScrollOrResize, true);
      cancelAnimationFrame(rafId);
    };
  }, [isOpen, updatePosition]);

  // Close on outside pointer click
  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (e) => {
      const inMenu = menuRef.current?.contains(e.target);
      const inTrigger = triggerRef.current?.contains(e.target);
      if (!inMenu && !inTrigger) {
        setIsOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [isOpen, setIsOpen]);

  // Focus management: move focus to first item on open, return to trigger on close
  useEffect(() => {
    if (isOpen) {
      const rafId = requestAnimationFrame(() => {
        setFocusedIndex(0);
        itemRefs.current[0]?.focus();
      });
      return () => cancelAnimationFrame(rafId);
    } else if (wasOpenRef.current) {
      triggerRef.current?.focus();
    }
    wasOpenRef.current = isOpen;
  }, [isOpen]);

  const menuItems = [
    {
      id: 'shortcuts-item',
      label: 'Keyboard shortcuts',
      icon: Keyboard,
      shortcut: '?',
      danger: false,
      onClick: () => {
        setIsOpen(false);
        onOpenShortcuts?.();
      },
    },
    {
      id: 'command-palette-item',
      label: 'Command palette',
      icon: Command,
      shortcut: 'Ctrl K',
      danger: false,
      onClick: () => {
        setIsOpen(false);
        onOpenPalette?.();
      },
    },
    {
      id: 'logout-btn',
      label: 'Sign out',
      icon: LogOut,
      shortcut: null,
      danger: true,
      onClick: () => {
        setIsOpen(false);
        onLogout?.();
      },
    },
  ];

  // Keyboard navigation within menu
  const handleKeyDown = (e) => {
    const total = menuItems.length;

    switch (e.key) {
      case 'ArrowDown': {
        e.preventDefault();
        const next = (focusedIndex + 1) % total;
        setFocusedIndex(next);
        itemRefs.current[next]?.focus();
        break;
      }
      case 'ArrowUp': {
        e.preventDefault();
        const prev = (focusedIndex - 1 + total) % total;
        setFocusedIndex(prev);
        itemRefs.current[prev]?.focus();
        break;
      }
      case 'Home': {
        e.preventDefault();
        setFocusedIndex(0);
        itemRefs.current[0]?.focus();
        break;
      }
      case 'End': {
        e.preventDefault();
        setFocusedIndex(total - 1);
        itemRefs.current[total - 1]?.focus();
        break;
      }
      case 'Escape': {
        e.preventDefault();
        setIsOpen(false);
        triggerRef.current?.focus();
        break;
      }
      case 'Tab': {
        setIsOpen(false);
        break;
      }
      default:
        break;
    }
  };

  const handleToggle = () => {
    setIsOpen((prev) => !prev);
  };

  const initial = user?.username?.[0]?.toUpperCase() || 'U';

  // Render trigger button based on variant
  const renderTrigger = () => {
    if (variant === 'rail') {
      const button = (
        <button
          ref={triggerRef}
          id={`${id}-trigger`}
          className={`user-menu__trigger user-menu__trigger--rail ${
            isOpen ? 'user-menu__trigger--open' : ''
          }`}
          onClick={handleToggle}
          aria-haspopup="menu"
          aria-expanded={isOpen}
          aria-label="User menu"
          type="button"
        >
          <User size={18} />
        </button>
      );

      if (tooltipText && !isOpen) {
        return (
          <Tooltip content={tooltipText} placement="right">
            {button}
          </Tooltip>
        );
      }
      return button;
    }

    // Default: 'topbar' variant
    return (
      <button
        ref={triggerRef}
        id={`${id}-trigger`}
        className={`user-menu__trigger user-menu__trigger--topbar ${
          isOpen ? 'user-menu__trigger--open' : ''
        }`}
        onClick={handleToggle}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="User menu"
        type="button"
      >
        <span className="user-menu__trigger-avatar">{initial}</span>
        <span className="user-menu__trigger-username">{user?.username}</span>
        <span
          className={`user-menu__chevron ${
            isOpen ? 'user-menu__chevron--open' : ''
          }`}
        >
          <ChevronDown size={14} />
        </span>
      </button>
    );
  };

  return (
    <>
      {renderTrigger()}

      {typeof document !== 'undefined' &&
        createPortal(
          <AnimatePresence>
            {isOpen && (
              <motion.div
                ref={menuRef}
                className="user-menu__popover"
                role="menu"
                aria-label="User account menu"
                onKeyDown={handleKeyDown}
                initial={
                  shouldReduceMotion
                    ? { opacity: 0 }
                    : { opacity: 0, scale: 0.96, y: -4 }
                }
                animate={
                  shouldReduceMotion
                    ? { opacity: 1 }
                    : { opacity: 1, scale: 1, y: 0 }
                }
                exit={
                  shouldReduceMotion
                    ? { opacity: 0, transition: { duration: 0 } }
                    : {
                        opacity: 0,
                        scale: 0.98,
                        y: -2,
                        transition: { duration: 0.08, ease: 'easeIn' },
                      }
                }
                transition={
                  shouldReduceMotion
                    ? { duration: 0 }
                    : { duration: 0.14, ease: [0.16, 1, 0.3, 1] }
                }
                style={{
                  top: `${coords.top}px`,
                  left: `${coords.left}px`,
                  transformOrigin: coords.transformOrigin,
                }}
              >
                {/* Header block */}
                <div className="user-menu__header">
                  <div className="user-menu__avatar-large" aria-hidden="true">
                    {initial}
                  </div>
                  <div className="user-menu__user-info">
                    <span className="user-menu__username" title={user?.username}>
                      {user?.username}
                    </span>
                    {health === false ? (
                      <div
                        className="user-menu__status-row"
                        aria-label="Status: Offline"
                      >
                        <span
                          className="user-menu__status-dot user-menu__status-dot--offline"
                          aria-hidden="true"
                        />
                        <span className="user-menu__status-text user-menu__status-text--offline">
                          Offline
                        </span>
                      </div>
                    ) : (
                      <div
                        className="user-menu__status-row"
                        aria-label={`Status: Signed in${
                          health === true ? ', Connected' : ''
                        }`}
                      >
                        <span
                          className="user-menu__status-dot user-menu__status-dot--online"
                          aria-hidden="true"
                        />
                        <span className="user-menu__status-text">
                          Signed in
                        </span>
                        <span className="user-menu__status-sub">
                          {health === false ? '' : ' · Connected'}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Items */}
                <div className="user-menu__items">
                  {/* Item 0: Shortcuts */}
                  {(() => {
                    const item = menuItems[0];
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.id}
                        ref={(el) => (itemRefs.current[0] = el)}
                        id={item.id}
                        role="menuitem"
                        tabIndex={focusedIndex === 0 ? 0 : -1}
                        className="user-menu__item"
                        onClick={item.onClick}
                        type="button"
                      >
                        <span className="user-menu__item-icon">
                          <Icon size={16} />
                        </span>
                        <span className="user-menu__item-label">
                          {item.label}
                        </span>
                        <span className="user-menu__item-shortcut">
                          <Kbd>{item.shortcut}</Kbd>
                        </span>
                      </button>
                    );
                  })()}

                  {/* Item 1: Command Palette */}
                  {(() => {
                    const item = menuItems[1];
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.id}
                        ref={(el) => (itemRefs.current[1] = el)}
                        id={item.id}
                        role="menuitem"
                        tabIndex={focusedIndex === 1 ? 0 : -1}
                        className="user-menu__item"
                        onClick={item.onClick}
                        type="button"
                      >
                        <span className="user-menu__item-icon">
                          <Icon size={16} />
                        </span>
                        <span className="user-menu__item-label">
                          {item.label}
                        </span>
                        <span className="user-menu__item-shortcut">
                          <Kbd>{item.shortcut}</Kbd>
                        </span>
                      </button>
                    );
                  })()}

                  {/* Divider */}
                  <div className="user-menu__divider" role="separator" />

                  {/* Item 2: Sign out */}
                  {(() => {
                    const item = menuItems[2];
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.id}
                        ref={(el) => (itemRefs.current[2] = el)}
                        id={item.id}
                        role="menuitem"
                        tabIndex={focusedIndex === 2 ? 0 : -1}
                        className="user-menu__item user-menu__item--danger"
                        onClick={item.onClick}
                        type="button"
                      >
                        <span className="user-menu__item-icon">
                          <Icon size={16} />
                        </span>
                        <span className="user-menu__item-label">
                          {item.label}
                        </span>
                      </button>
                    );
                  })()}
                </div>
              </motion.div>
            )}
          </AnimatePresence>,
          document.body
        )}
    </>
  );
}

export default UserMenu;
