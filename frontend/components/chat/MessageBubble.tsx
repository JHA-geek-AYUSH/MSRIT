'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import type { ChatMessage, ToolExecutionCard, ComplianceTriageResult } from '@/types/chat';

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  if (isSystem) return null;

  return (
    <div className={cn('flex gap-3 px-1 py-2', isUser ? 'justify-end' : 'justify-start')}>
      {/* Avatar */}
      {!isUser && (
        <div className="size-8 rounded-full bg-gradient-to-br from-amber-600 to-amber-800 flex items-center justify-center shrink-0 mt-0.5">
          <span className="text-white text-[10px] font-bold">OP</span>
        </div>
      )}

      <div className={cn('max-w-[80%] space-y-2', isUser && 'order-first')}>
        {/* Message Content */}
        <div
          className={cn(
            'rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
            isUser
              ? 'bg-primary text-primary-foreground rounded-br-md'
              : 'bg-card border border-border/40 text-foreground rounded-bl-md',
          )}
        >
          {message.status === 'thinking' ? (
            <div className="flex items-center gap-2 py-1">
              <span className="text-muted-foreground">Thinking</span>
              <span className="flex gap-0.5">
                <span className="size-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="size-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="size-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
            </div>
          ) : (
            <div className="whitespace-pre-wrap">{message.content}</div>
          )}
        </div>

        {/* Tool Executions */}
        {message.toolExecutions && message.toolExecutions.length > 0 && (
          <div className="space-y-1.5">
            {message.toolExecutions.map((tool, idx) => (
              <ToolExecutionBadge key={idx} tool={tool} />
            ))}
          </div>
        )}

        {/* Auth Required */}
        {message.authInfo && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 space-y-2">
            <div className="flex items-center gap-2 text-amber-600 text-xs font-medium">
              <svg className="size-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m0 0v2m0-2h2m-2 0H10m9.364-7.364A9 9 0 1112 3a9 9 0 017.364 4.636z" />
              </svg>
              Integration Required
            </div>
            <p className="text-xs text-muted-foreground">{message.authInfo.message}</p>
            {message.authInfo.authUrl && (
              <a
                href={message.authInfo.authUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors"
              >
                Connect {message.authInfo.toolkit.toUpperCase()}
                <svg className="size-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </a>
            )}
          </div>
        )}

        {/* Compliance Result */}
        {message.complianceResult && (
          <ComplianceReport result={message.complianceResult} />
        )}
      </div>

      {/* User Avatar */}
      {isUser && (
        <div className="size-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5 border border-primary/20">
          <svg className="size-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        </div>
      )}
    </div>
  );
}

function ToolExecutionBadge({ tool }: { tool: ToolExecutionCard }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={cn(
        'rounded-xl border px-3 py-2 text-xs transition-all cursor-pointer',
        tool.status === 'running' && 'border-blue-500/30 bg-blue-500/5',
        tool.status === 'done' && 'border-green-500/30 bg-green-500/5',
        tool.status === 'error' && 'border-red-500/30 bg-red-500/5',
      )}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {tool.status === 'running' && (
            <svg className="size-3.5 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {tool.status === 'done' && (
            <svg className="size-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          )}
          {tool.status === 'error' && (
            <svg className="size-3.5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          )}
          <span className="font-medium text-foreground/80">{tool.tool}</span>
        </div>
        <span className="text-muted-foreground">{expanded ? '▲' : '▼'}</span>
      </div>
      {expanded && tool.formattedResult && (
        <div className="mt-2 pt-2 border-t border-border/30 text-muted-foreground whitespace-pre-wrap font-mono text-[10px] leading-relaxed max-h-32 overflow-auto">
          {tool.formattedResult}
        </div>
      )}
    </div>
  );
}

function ComplianceReport({ result }: { result: ComplianceTriageResult }) {
  const [expanded, setExpanded] = useState(false);
  const ratingColor = {
    high: 'text-red-500 bg-red-500/10 border-red-500/30',
    medium: 'text-amber-500 bg-amber-500/10 border-amber-500/30',
    low: 'text-green-500 bg-green-500/10 border-green-500/30',
  }[result.overall_rating] || 'text-muted-foreground bg-muted/50 border-border/50';

  return (
    <div className="rounded-xl border border-border/50 bg-card overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-3 flex items-center justify-between hover:bg-muted/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg className="size-4 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <span className="text-xs font-semibold">Compliance Report</span>
        </div>
        <div className={cn('px-2 py-0.5 rounded-full text-[10px] font-bold border', ratingColor)}>
          {result.overall_rating.toUpperCase()}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-3">
          {/* Domain Scores */}
          <div className="grid gap-1.5">
            {result.domains.map((domain, i) => (
              <div key={i} className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-muted/30 text-xs">
                <span className="font-medium">{domain.name}</span>
                <div className="flex items-center gap-2">
                  <div className={cn(
                    'size-2 rounded-full',
                    domain.rating === 'high' ? 'bg-red-500' : domain.rating === 'medium' ? 'bg-amber-500' : 'bg-green-500',
                  )} />
                  <span className="text-muted-foreground">{Math.round(domain.confidence * 100)}%</span>
                </div>
              </div>
            ))}
          </div>

          {/* STR/EDD Flags */}
          {(result.requires_str || result.requires_edd) && (
            <div className="space-y-1">
              {result.requires_str && (
                <div className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-600 font-medium">
                  <svg className="size-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 21v-4m0 0V5a2 2 0 012-2h6.5l1 1H21l-3 6 3 6h-8.5l-1-1H5a2 2 0 00-2 2zm9-13.5V9" />
                  </svg>
                  STR Filing Required — File within 7 working days
                </div>
              )}
              {result.requires_edd && (
                <div className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-600 font-medium">
                  <svg className="size-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.052 16.5c-.77.833.192 2.5 1.732 2.5z" />
                  </svg>
                  Enhanced Due Diligence Recommended
                </div>
              )}
            </div>
          )}

          {/* Recommendations */}
          {result.recommendations.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Recommendations</p>
              <ul className="space-y-1">
                {result.recommendations.slice(0, 3).map((rec, i) => (
                  <li key={i} className="text-xs text-muted-foreground flex gap-2">
                    <span className="text-primary shrink-0">{i + 1}.</span>
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
