'use client';

// Simple reactive store using React's built-in primitives
// No external dependencies needed

import { useSyncExternalStore } from 'react';

// ── Store Types ──────────────────────────────────────────────

interface StoreState {
  sidebarOpen: boolean;
  activeTab: string;
  theme: 'dark' | 'light';
  isChatProcessing: boolean;
}

type Listener = () => void;

let state: StoreState = {
  sidebarOpen: false,
  activeTab: 'chat',
  theme: 'dark',
  isChatProcessing: false,
};

const listeners = new Set<Listener>();

function getSnapshot(): StoreState {
  return state;
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setState(partial: Partial<StoreState>) {
  state = { ...state, ...partial };
  listeners.forEach((l) => l());
}

// ── React Hook ───────────────────────────────────────────────

export function useAppStore<R>(selector: (s: StoreState) => R): R {
  return useSyncExternalStore(
    subscribe,
    () => selector(getSnapshot()),
    () => selector(getSnapshot()),
  );
}

// ── Actions ──────────────────────────────────────────────────

export const storeActions = {
  toggleSidebar: () => setState({ sidebarOpen: !state.sidebarOpen }),
  setSidebarOpen: (open: boolean) => setState({ sidebarOpen: open }),
  setActiveTab: (tab: string) => setState({ activeTab: tab }),
  setTheme: (theme: 'dark' | 'light') => {
    setState({ theme });
    if (typeof document !== 'undefined') {
      document.documentElement.classList.toggle('dark', theme === 'dark');
    }
  },
  setChatProcessing: (processing: boolean) => setState({ isChatProcessing: processing }),
  getState: () => state,
};
