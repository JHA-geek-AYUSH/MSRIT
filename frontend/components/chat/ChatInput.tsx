'use client';

import { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
  isThinking: boolean;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  onStop,
  isThinking,
  disabled,
  placeholder = 'Ask GemmaFinOS anything...',
}: ChatInputProps) {
  const [value, setValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [value]);

  const handleSubmit = () => {
    if (value.trim() && !isThinking && onSend) {
      onSend(value.trim());
      setValue('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-border/40 bg-background/95 backdrop-blur-xl">
      <div className="max-w-4xl mx-auto px-4 py-3">
        <div
          className={cn(
            'relative flex items-end gap-2 rounded-2xl border bg-card transition-all duration-200',
            isFocused ? 'border-primary/40 shadow-lg shadow-primary/5' : 'border-border/50',
          )}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={1}
            disabled={disabled}
            className="flex-1 bg-transparent border-0 outline-none resize-none text-sm text-foreground placeholder:text-muted-foreground/60 px-4 py-3 min-h-[44px] max-h-[200px]"
          />

          {isThinking ? (
            <button
              onClick={onStop}
              className="size-9 rounded-xl bg-destructive/10 text-destructive hover:bg-destructive/20 flex items-center justify-center shrink-0 mr-1.5 mb-1.5 transition-colors"
            >
              <svg className="size-4" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="1" />
              </svg>
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={!value.trim()}
              className={cn(
                'size-9 rounded-xl flex items-center justify-center shrink-0 mr-1.5 mb-1.5 transition-all',
                value.trim()
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm'
                  : 'bg-muted text-muted-foreground',
              )}
            >
              <svg className="size-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          )}
        </div>

        {isFocused && !isThinking && (
          <p className="mt-1.5 text-[10px] text-muted-foreground/50 text-center">
            Enter to send · Shift + Enter for new line
          </p>
        )}
      </div>
    </div>
  );
}
