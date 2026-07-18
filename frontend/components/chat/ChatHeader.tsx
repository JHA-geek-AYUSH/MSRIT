'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';

interface ChatHeaderProps {
  isThinking: boolean;
  onClear: () => void;
  onNew: () => void;
}

export function ChatHeader({ isThinking, onClear, onNew }: ChatHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="sticky top-0 z-40 bg-cream-100/90 backdrop-blur-xl border-b border-brown-500/15">
      <div className="flex items-center justify-between px-4 py-3 max-w-4xl mx-auto">
        <div className="flex items-center gap-3">
          <div className="size-8 rounded-lg bg-brown-900 flex items-center justify-center">
            <span className="text-cream-50 text-xs font-bold font-display">GF</span>
          </div>
          <div>
            <h1 className="text-sm font-semibold font-display text-brown-900">GemmaFin Assistant</h1>
            <p className="text-[10px] text-brown-500 font-body">
              {isThinking ? 'Thinking…' : 'Financial Compliance AI'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onNew}
            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
          >
            New Chat
          </button>
          <div className="relative">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="size-8 rounded-lg hover:bg-muted flex items-center justify-center transition-colors"
            >
              <svg className="size-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01" />
              </svg>
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-full mt-1 w-48 bg-card border border-border/50 rounded-xl shadow-lg overflow-hidden z-50">
                <button
                  onClick={() => { onClear(); setMenuOpen(false); }}
                  className="w-full px-4 py-2.5 text-xs text-left hover:bg-muted transition-colors flex items-center gap-2"
                >
                  <svg className="size-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Clear conversation
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
