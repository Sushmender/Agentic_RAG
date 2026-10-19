/**
 * frontend/src/context/ChatContext.jsx
 * Persistent multi-tab chat store placed above the router.
 * State survives page navigation across Documents, Metrics, Evaluation, etc.
 */

import {
  createContext,
  useContext,
  useReducer,
  useEffect,
  useRef,
  useCallback,
} from 'react';
import { toast } from 'sonner';
import { queryAPI, healthAPI } from '../services/api';
import { useAuth } from './AuthContext';

const MAX_TABS = 10;

export function createDefaultTab() {
  return {
    id: 'default',
    title: 'Chat',
    createdAt: 0,
    messages: [],
    docIds: [],
    model: 'groq',
    draft: '',
    activeMessageId: null,
    evidenceTab: 'sources',
    hasUnread: false,
    docNotice: null,
  };
}

export function createNewTab(overrides = {}) {
  const id = `tab_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
  return {
    id,
    title: 'New chat',
    createdAt: Date.now(),
    messages: [],
    docIds: [],
    model: 'groq',
    draft: '',
    activeMessageId: null,
    evidenceTab: 'sources',
    hasUnread: false,
    docNotice: null,
    ...overrides,
  };
}

export const initialChatState = {
  tabs: [createDefaultTab()],
  activeTabId: 'default',
  bootId: null,
};

// Pure exported reducer
export function chatReducer(state, action) {
  switch (action.type) {
    case 'NEW_TAB': {
      if (state.tabs.length >= MAX_TABS) {
        return state;
      }
      const newTab = createNewTab(action.payload || {});
      const activate = action.payload?.activate !== false;
      return {
        ...state,
        tabs: [...state.tabs, newTab],
        activeTabId: activate ? newTab.id : state.activeTabId,
      };
    }

    case 'RESTORE_TAB': {
      const { tab, index } = action.payload;
      if (!tab || tab.id === 'default') return state;
      // Do not exceed max tabs if possible
      if (state.tabs.length >= MAX_TABS) {
        return state;
      }
      const insertAt = typeof index === 'number' && index >= 0 && index <= state.tabs.length
        ? index
        : state.tabs.length;
      const nextTabs = [...state.tabs];
      nextTabs.splice(insertAt, 0, tab);
      return {
        ...state,
        tabs: nextTabs,
        activeTabId: tab.id,
      };
    }

    case 'CLOSE_TAB': {
      const { tabId } = action.payload;
      if (tabId === 'default') return state; // Default tab can NEVER be closed

      const index = state.tabs.findIndex((t) => t.id === tabId);
      if (index === -1) return state;

      const remainingTabs = state.tabs.filter((t) => t.id !== tabId);
      let nextActiveId = state.activeTabId;

      if (state.activeTabId === tabId) {
        // Activate right neighbor, else left, else default
        if (index < remainingTabs.length) {
          nextActiveId = remainingTabs[index].id;
        } else if (index - 1 >= 0) {
          nextActiveId = remainingTabs[index - 1].id;
        } else {
          nextActiveId = 'default';
        }
      }

      return {
        ...state,
        tabs: remainingTabs,
        activeTabId: nextActiveId,
      };
    }

    case 'SET_ACTIVE': {
      const { tabId } = action.payload;
      if (!state.tabs.some((t) => t.id === tabId)) return state;

      return {
        ...state,
        activeTabId: tabId,
        tabs: state.tabs.map((tab) =>
          tab.id === tabId ? { ...tab, hasUnread: false } : tab
        ),
      };
    }

    case 'RENAME_TAB': {
      const { tabId, title } = action.payload;
      const cleanTitle = (title || '').trim();
      if (!cleanTitle) return state;

      return {
        ...state,
        tabs: state.tabs.map((tab) =>
          tab.id === tabId ? { ...tab, title: cleanTitle } : tab
        ),
      };
    }

    case 'UPDATE_TAB': {
      const { tabId, updates } = action.payload;
      return {
        ...state,
        tabs: state.tabs.map((tab) =>
          tab.id === tabId ? { ...tab, ...updates } : tab
        ),
      };
    }

    case 'ADD_MESSAGE': {
      const { tabId, message } = action.payload;
      return {
        ...state,
        tabs: state.tabs.map((tab) => {
          if (tab.id !== tabId) return tab;

          let updatedTitle = tab.title;
          // Auto-title on first question if title is "New chat"
          if (
            message.type === 'user' &&
            tab.title === 'New chat'
          ) {
            const raw = message.content.trim();
            updatedTitle = raw.length > 28 ? `${raw.slice(0, 28)}…` : raw;
          }

          return {
            ...tab,
            title: updatedTitle,
            messages: [...tab.messages, message],
          };
        }),
      };
    }

    case 'UPDATE_MESSAGE': {
      const { tabId, messageId, updates } = action.payload;
      return {
        ...state,
        tabs: state.tabs.map((tab) => {
          if (tab.id !== tabId) return tab;
          return {
            ...tab,
            messages: tab.messages.map((msg) =>
              msg.id === messageId ? { ...msg, ...updates } : msg
            ),
          };
        }),
      };
    }

    case 'CLEAR_TAB': {
      const { tabId } = action.payload;
      return {
        ...state,
        tabs: state.tabs.map((tab) => {
          if (tab.id !== tabId) return tab;
          return {
            ...tab,
            messages: [],
            draft: '',
            activeMessageId: null,
          };
        }),
      };
    }

    case 'REORDER_TABS': {
      const { newTabs } = action.payload;
      if (!Array.isArray(newTabs)) return state;

      // Default tab stays first and cannot be moved
      const defaultTab = state.tabs.find((t) => t.id === 'default') || createDefaultTab();
      const nonDefaultTabs = newTabs.filter((t) => t.id !== 'default');

      return {
        ...state,
        tabs: [defaultTab, ...nonDefaultTabs],
      };
    }

    case 'SET_BOOT_ID': {
      return {
        ...state,
        bootId: action.payload.bootId,
      };
    }

    case 'RESET_ALL': {
      return {
        ...initialChatState,
        bootId: action.payload?.bootId ?? state.bootId,
      };
    }

    case 'LOAD_SAVED': {
      const { savedState } = action.payload;
      if (!savedState) return state;

      let loadedTabs = Array.isArray(savedState.tabs) ? savedState.tabs : [];
      // Ensure default tab exists
      if (!loadedTabs.some((t) => t.id === 'default')) {
        loadedTabs.unshift(createDefaultTab());
      }

      // Convert any pending messages to interrupted error messages
      loadedTabs = loadedTabs.map((tab) => ({
        ...tab,
        messages: (tab.messages || []).map((m) => {
          if (m.pending) {
            return {
              ...m,
              pending: false,
              error: 'Interrupted, regenerate to retry',
              revealed: true,
            };
          }
          return {
            ...m,
            revealed: true, // past messages are already revealed
          };
        }),
      }));

      const activeId = loadedTabs.some((t) => t.id === savedState.activeTabId)
        ? savedState.activeTabId
        : 'default';

      return {
        tabs: loadedTabs,
        activeTabId: activeId,
        bootId: savedState.boot_id || null,
      };
    }

    default:
      return state;
  }
}

// Storage helpers with quota fallback
function getStorageKey(user) {
  const uid = user?.user_id || 'guest';
  return `rag_chats_${uid}`;
}

function saveStoreToLocalStorage(key, state) {
  if (!key) return;

  const payload = {
    boot_id: state.bootId,
    activeTabId: state.activeTabId,
    tabs: state.tabs.map((tab) => ({
      ...tab,
      messages: tab.messages.map((m) =>
        m.pending
          ? {
              ...m,
              pending: false,
              error: 'Interrupted, regenerate to retry',
              revealed: true,
            }
          : { ...m, revealed: true }
      ),
    })),
  };

  try {
    localStorage.setItem(key, JSON.stringify(payload));
  } catch {
    // Quota exceeded: first drop source payloads from oldest tabs
    try {
      const cloned = JSON.parse(JSON.stringify(payload));
      for (let i = 0; i < cloned.tabs.length; i++) {
        cloned.tabs[i].messages.forEach((m) => {
          if (m.result?.sources) {
            m.result = { ...m.result, sources: [] };
          }
        });
      }
      localStorage.setItem(key, JSON.stringify(cloned));
    } catch {
      // Then drop oldest messages
      try {
        const cloned = JSON.parse(JSON.stringify(payload));
        cloned.tabs.forEach((tab) => {
          if (tab.messages.length > 4) {
            tab.messages = tab.messages.slice(-4);
          }
        });
        localStorage.setItem(key, JSON.stringify(cloned));
      } catch {
        // Never throw
      }
    }
  }
}

const ChatContext = createContext(null);

export function ChatProvider({ children }) {
  const { user } = useAuth();
  const [state, dispatch] = useReducer(chatReducer, initialChatState);

  const stateRef = useRef(state);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const abortControllersRef = useRef(new Map()); // messageId -> AbortController
  const isLoadedRef = useRef(false);
  const saveTimeoutRef = useRef(null);

  // Load from localStorage on user change
  useEffect(() => {
    if (!user) {
      dispatch({ type: 'RESET_ALL' });
      isLoadedRef.current = true;
      return;
    }
    const key = getStorageKey(user);
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw);
        dispatch({ type: 'LOAD_SAVED', payload: { savedState: parsed } });
      } else {
        dispatch({ type: 'RESET_ALL' });
      }
    } catch {
      dispatch({ type: 'RESET_ALL' });
    } finally {
      isLoadedRef.current = true;
    }
  }, [user]);

  // Debounced persistence to localStorage (~300ms)
  useEffect(() => {
    if (!isLoadedRef.current) return;
    const key = getStorageKey(user);

    clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(() => {
      saveStoreToLocalStorage(key, state);
    }, 300);

    return () => clearTimeout(saveTimeoutRef.current);
  }, [state, user]);

  // Backend restart detection: poll health endpoint
  const checkBackendBootId = useCallback(async () => {
    try {
      const res = await healthAPI.check();
      const serverBootId = res.data?.boot_id;
      if (!serverBootId) return;

      const currentBootId = stateRef.current.bootId;
      if (!currentBootId) {
        // First boot id recorded
        dispatch({ type: 'SET_BOOT_ID', payload: { bootId: serverBootId } });
      } else if (currentBootId !== serverBootId) {
        // Backend was restarted: wipe chats, store new boot_id
        dispatch({ type: 'RESET_ALL', payload: { bootId: serverBootId } });
        const key = getStorageKey(user);
        try {
          localStorage.removeItem(key);
        } catch {}
      }
    } catch {
      // If backend is unreachable, NEVER wipe
    }
  }, [user]);

  useEffect(() => {
    checkBackendBootId();
    const timer = setInterval(checkBackendBootId, 30_000);
    return () => clearInterval(timer);
  }, [checkBackendBootId]);

  // Actions
  const newTab = useCallback((options = {}) => {
    if (stateRef.current.tabs.length >= MAX_TABS) {
      toast.info('Close a chat to open a new one');
      return null;
    }
    dispatch({ type: 'NEW_TAB', payload: options });
    return true;
  }, []);

  const closeTab = useCallback((tabId) => {
    if (tabId === 'default') return;

    const currentTabs = stateRef.current.tabs;
    const tabIndex = currentTabs.findIndex((t) => t.id === tabId);
    if (tabIndex === -1) return;

    const tab = currentTabs[tabIndex];

    // Abort pending requests in this tab
    tab.messages.forEach((msg) => {
      if (msg.pending && abortControllersRef.current.has(msg.id)) {
        abortControllersRef.current.get(msg.id).abort();
        abortControllersRef.current.delete(msg.id);
      }
    });

    dispatch({ type: 'CLOSE_TAB', payload: { tabId } });

    // Show undo toast if tab had messages
    if (tab.messages.length > 0) {
      toast('Chat closed', {
        duration: 6000,
        action: {
          label: 'Undo',
          onClick: () => {
            dispatch({
              type: 'RESTORE_TAB',
              payload: { tab, index: tabIndex },
            });
          },
        },
      });
    }
  }, []);

  const setActive = useCallback((tabId) => {
    dispatch({ type: 'SET_ACTIVE', payload: { tabId } });
  }, []);

  const renameTab = useCallback((tabId, title) => {
    dispatch({ type: 'RENAME_TAB', payload: { tabId, title } });
  }, []);

  const updateTab = useCallback((tabId, updates) => {
    dispatch({ type: 'UPDATE_TAB', payload: { tabId, updates } });
  }, []);

  const addMessage = useCallback((tabId, message) => {
    dispatch({ type: 'ADD_MESSAGE', payload: { tabId, message } });
  }, []);

  const updateMessage = useCallback((tabId, messageId, updates) => {
    dispatch({ type: 'UPDATE_MESSAGE', payload: { tabId, messageId, updates } });
  }, []);

  const clearTab = useCallback((tabId) => {
    dispatch({ type: 'CLEAR_TAB', payload: { tabId } });
  }, []);

  const reorderTabs = useCallback((newTabs) => {
    dispatch({ type: 'REORDER_TABS', payload: { newTabs } });
  }, []);

  const resetAll = useCallback(() => {
    dispatch({ type: 'RESET_ALL' });
  }, []);

  const markMessageRevealed = useCallback((tabId, messageId) => {
    dispatch({
      type: 'UPDATE_MESSAGE',
      payload: { tabId, messageId, updates: { revealed: true } },
    });
  }, []);

  // Send message implementation with AbortController
  const sendMessage = useCallback(
    async ({ tabId, queryText, regenerateMessageId = null }) => {
      const q = (queryText || '').trim();
      if (!q) return;

      const currentTab = stateRef.current.tabs.find((t) => t.id === tabId);
      if (!currentTab) return;

      const docIds = currentTab.docIds || [];
      const model = currentTab.model || 'groq';

      const assistantMsgId =
        regenerateMessageId ||
        `msg_a_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;

      if (regenerateMessageId) {
        // Abort previous if pending
        if (abortControllersRef.current.has(regenerateMessageId)) {
          abortControllersRef.current.get(regenerateMessageId).abort();
          abortControllersRef.current.delete(regenerateMessageId);
        }
        dispatch({
          type: 'UPDATE_MESSAGE',
          payload: {
            tabId,
            messageId: regenerateMessageId,
            updates: {
              pending: true,
              error: null,
              content: '',
              result: null,
              revealed: false,
            },
          },
        });
      } else {
        const userMsgId = `msg_u_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
        dispatch({
          type: 'ADD_MESSAGE',
          payload: {
            tabId,
            message: { id: userMsgId, type: 'user', content: q },
          },
        });
        dispatch({
          type: 'ADD_MESSAGE',
          payload: {
            tabId,
            message: {
              id: assistantMsgId,
              type: 'assistant',
              content: '',
              result: null,
              pending: true,
              error: null,
              revealed: false,
            },
          },
        });
        // Clear composer draft
        dispatch({
          type: 'UPDATE_TAB',
          payload: { tabId, updates: { draft: '' } },
        });
      }

      const controller = new AbortController();
      abortControllersRef.current.set(assistantMsgId, controller);

      try {
        const res = await queryAPI.query(
          {
            query: q,
            document_ids: docIds.length > 0 ? docIds : null,
            llm_provider: model,
          },
          { signal: controller.signal }
        );

        dispatch({
          type: 'UPDATE_MESSAGE',
          payload: {
            tabId,
            messageId: assistantMsgId,
            updates: {
              content: res.data.answer,
              result: res.data,
              pending: false,
              error: null,
              revealed: false,
            },
          },
        });

        // Check if tab is currently active
        const isActiveTab = stateRef.current.activeTabId === tabId;
        dispatch({
          type: 'UPDATE_TAB',
          payload: {
            tabId,
            updates: {
              activeMessageId: assistantMsgId,
              hasUnread: !isActiveTab,
              evidenceTab: 'sources',
            },
          },
        });
      } catch (err) {
        if (
          err.name === 'CanceledError' ||
          err.code === 'ERR_CANCELED' ||
          controller.signal.aborted
        ) {
          // In-flight query was intentionally cancelled
          return;
        }

        const isTimeout =
          err.code === 'ECONNABORTED' ||
          err.name === 'TimeoutError' ||
          err.message?.toLowerCase().includes('timeout');

        const status = err.response?.status;
        const detail =
          err.response?.data?.detail || err.message || 'Query failed.';
        let msg = detail;

        if (isTimeout) {
          msg = 'The model took too long to respond. Try again or switch model.';
        } else if (status === 429) {
          msg = 'Rate limit reached — wait a moment and try again.';
        } else if (status >= 500) {
          msg = `Server error: ${detail}`;
        }

        dispatch({
          type: 'UPDATE_MESSAGE',
          payload: {
            tabId,
            messageId: assistantMsgId,
            updates: {
              pending: false,
              error: msg,
              revealed: true,
            },
          },
        });

        // Show toast for non-timeout errors; timeouts are shown once inline
        if (!isTimeout) {
          toast.error(msg);
        }
      } finally {
        abortControllersRef.current.delete(assistantMsgId);
      }
    },
    []
  );

  const activeTab =
    state.tabs.find((t) => t.id === state.activeTabId) ||
    state.tabs[0] ||
    createDefaultTab();

  const value = {
    tabs: state.tabs,
    activeTabId: state.activeTabId,
    activeTab,
    bootId: state.bootId,
    newTab,
    closeTab,
    setActive,
    renameTab,
    updateTab,
    addMessage,
    updateMessage,
    clearTab,
    reorderTabs,
    resetAll,
    sendMessage,
    markMessageRevealed,
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) {
    throw new Error('useChat must be used within ChatProvider');
  }
  return ctx;
}
