'use client';

import { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { sendComplianceChat } from '@/lib/compliance-api';

interface Message {
  role: 'user' | 'agent';
  content: string;
}

interface ComplianceChatProps {
  sessionContext: Record<string, any>;
}

const SUGGESTED_PROMPTS = [
  "What does this risk tier mean?",
  "What if the cash ratio doubles?",
  "Which rules were breached?",
  "Simulate the worst-case penalty",
  "Generate a compliance report",
];

export function ComplianceChat({ sessionContext }: ComplianceChatProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'agent',
      content: 'Hi! I\'m your **Compliance Orchestrator**. I can explain risk tiers, run penalty simulations, compare scenarios, or generate reports. What would you like to explore?'
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async (text?: string) => {
    const msg = (text || input).trim();
    if (!msg || loading) return;

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    setLoading(true);

    try {
      const response = await sendComplianceChat(msg, sessionContext);
      setMessages(prev => [...prev, { role: 'agent', content: response.reply }]);
    } catch (err: any) {
      setMessages(prev => [...prev, {
        role: 'agent',
        content: `**Error:** ${err.message}. Please try again or re-run the triage.`
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full border border-zinc-200 dark:border-zinc-800 rounded-xl overflow-hidden bg-white dark:bg-zinc-900 shadow-sm">
      {/* Header */}
      <div className="bg-gradient-to-r from-zinc-50 to-zinc-100 dark:from-zinc-800 dark:to-zinc-800/50 px-4 py-3 border-b border-zinc-200 dark:border-zinc-700">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-sm shadow-sm">
            🤖
          </div>
          <div>
            <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
              Compliance Orchestrator
            </h3>
            <p className="text-[10px] text-zinc-400">Ask about risks, penalties, or generate reports</p>
          </div>
          {loading && (
            <span className="ml-auto flex items-center gap-1.5 text-[10px] text-blue-500">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
              Thinking...
            </span>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[250px] max-h-[400px] scrollbar-thin">
        {/* Suggested prompts (only when no messages besides welcome) */}
        {messages.length === 1 && !loading && (
          <div className="mb-4">
            <p className="text-[10px] text-zinc-400 mb-2 uppercase tracking-wider font-medium">
              Suggested questions
            </p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTED_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => handleSend(prompt)}
                  className="text-[11px] text-zinc-600 dark:text-zinc-400 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 px-2.5 py-1.5 rounded-lg transition-colors"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={cn(
              "flex",
              m.role === 'user' ? 'justify-end' : 'justify-start',
              "animate-in fade-in slide-in-from-bottom-2 duration-200"
            )}
            style={{ animationDelay: `${i * 50}ms` }}
          >
            {m.role === 'agent' && (
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-[10px] mr-2 mt-1 shadow-sm">
                🤖
              </div>
            )}
            <div
              className={cn(
                "max-w-[80%] rounded-2xl px-3.5 py-2.5 text-sm whitespace-pre-wrap leading-relaxed shadow-sm",
                m.role === 'user'
                  ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white rounded-br-md'
                  : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200 rounded-bl-md border border-zinc-200/50 dark:border-zinc-700/50'
              )}
              style={{
                wordBreak: 'break-word',
              }}
            >
              {m.role === 'agent' ? (
                <span
                  dangerouslySetInnerHTML={{
                    __html: m.content
                      .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold">$1</strong>')
                      .replace(/\n/g, '<br/>')
                  }}
                />
              ) : (
                m.content
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-[10px] mr-2 mt-1 shadow-sm">
              🤖
            </div>
            <div className="bg-zinc-100 dark:bg-zinc-800 rounded-2xl rounded-bl-md px-4 py-3 border border-zinc-200/50 dark:border-zinc-700/50">
              <div className="flex gap-1">
                <span className="w-2 h-2 rounded-full bg-zinc-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 rounded-full bg-zinc-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 rounded-full bg-zinc-400 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Ask about risks, penalties, or generate reports..."
            disabled={loading}
            className={cn(
              "flex-1 text-sm bg-white dark:bg-zinc-950 border border-zinc-300 dark:border-zinc-700",
              "rounded-xl px-4 py-2.5",
              "focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "transition-all duration-200",
              "placeholder:text-zinc-400 dark:placeholder:text-zinc-600"
            )}
          />
          <button
            onClick={() => handleSend()}
            disabled={loading || !input.trim()}
            className={cn(
              "bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800",
              "text-white px-5 py-2.5 rounded-xl text-sm font-medium",
              "transition-all duration-200 shadow-sm hover:shadow-md",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "active:scale-[0.97]"
            )}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
