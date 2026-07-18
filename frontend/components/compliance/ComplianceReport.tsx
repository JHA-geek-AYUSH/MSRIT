'use client';

import { useState, useMemo } from 'react';
import { cn } from '@/lib/utils';

interface Props {
  report: string;
  runId: string;
}

function parseSections(text: string): { level: number; title: string; content: string[] }[] {
  const lines = text.split('\n');
  const sections: { level: number; title: string; content: string[] }[] = [];
  let current: { level: number; title: string; content: string[] } | null = null;

  for (const line of lines) {
    const h2Match = line.match(/^## (.+)/);
    const h3Match = line.match(/^### (.+)/);
    if (h2Match) {
      if (current) sections.push(current);
      current = { level: 2, title: h2Match[1], content: [] };
    } else if (h3Match) {
      if (current) sections.push(current);
      current = { level: 3, title: h3Match[1], content: [] };
    } else {
      if (current) current.content.push(line);
    }
  }
  if (current) sections.push(current);
  return sections;
}

function renderLine(line: string, i: number) {
  if (line.startsWith('|')) {
    const isHeader = line.includes('---');
    return (
      <div
        key={i}
        className={cn(
          'text-xs font-mono py-1',
          isHeader ? 'text-zinc-300 dark:text-zinc-600 border-b border-zinc-200 dark:border-zinc-700' : 'text-zinc-600 dark:text-zinc-400 border-b border-zinc-100 dark:border-zinc-800',
        )}
      >
        {line}
      </div>
    );
  }
  if (line.startsWith('---')) return <hr key={i} className="my-3 border-zinc-200 dark:border-zinc-700" />;
  if (!line.trim()) return <div key={i} className="h-2" />;

  // Bold markers
  const parts = line.split(/(\*\*[^*]+\*\*)/g);
  return (
    <p key={i} className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">
      {parts.map((p, j) =>
        p.startsWith('**') && p.endsWith('**')
          ? <strong key={j} className="text-zinc-900 dark:text-zinc-100 font-semibold">{p.slice(2, -2)}</strong>
          : p
      )}
    </p>
  );
}

export function ComplianceReport({ report, runId }: Props) {
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set());
  const [viewMode, setViewMode] = useState<'sections' | 'raw'>('sections');

  const sections = useMemo(() => parseSections(report), [report]);
  const lines = useMemo(() => report.split('\n'), [report]);

  const toggleSection = (idx: number) => {
    setExpandedSections(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  // Preview: show first 2 sections, rest collapsed
  const initialExpanded = new Set<number>();
  sections.slice(0, 2).forEach((_, i) => initialExpanded.add(i));

  // Merge initial + user toggled
  const visible = new Set(Array.from(initialExpanded).concat(Array.from(expandedSections)));

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-100 dark:border-zinc-800">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold text-sm text-zinc-800 dark:text-zinc-200 flex items-center gap-2">
            <span>📄</span>
            Compliance Report
          </h2>
          <span className="text-[10px] text-zinc-400 font-mono bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 rounded">
            #{runId.slice(0, 8)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewMode(viewMode === 'sections' ? 'raw' : 'sections')}
            className="text-[10px] text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors px-2 py-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            {viewMode === 'sections' ? 'Raw view' : 'Section view'}
          </button>
          <button
            onClick={() => {
              try { navigator.clipboard.writeText(report); } catch { /* ignore */ }
            }}
            className="text-[10px] text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors px-2 py-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800"
            title="Copy report"
          >
            📋 Copy
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="px-5 py-4 max-h-[600px] overflow-y-auto">
        {viewMode === 'raw' ? (
          <div className="space-y-0.5">
            {lines.map((l, i) => renderLine(l, i))}
          </div>
        ) : sections.length === 0 ? (
          <div className="space-y-0.5">
            {lines.slice(0, 12).map((l, i) => renderLine(l, i))}
            {lines.length > 12 && (
              <button
                onClick={() => setViewMode('raw')}
                className="mt-3 text-xs text-blue-600 dark:text-blue-400 hover:underline"
              >
                Show all ({lines.length - 12} more lines) →
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {sections.map((section, idx) => {
              const isExpanded = visible.has(idx);
              const contentPreview = section.content.slice(0, 3).join('\n');

              return (
                <div
                  key={idx}
                  className={cn(
                    "rounded-lg border border-zinc-100 dark:border-zinc-800 overflow-hidden transition-all duration-200",
                    isExpanded ? "bg-white dark:bg-zinc-900" : "bg-zinc-50/50 dark:bg-zinc-900/50",
                  )}
                >
                  <button
                    onClick={() => toggleSection(idx)}
                    className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "text-xs font-semibold",
                        section.level === 2 ? "text-zinc-800 dark:text-zinc-200" : "text-zinc-600 dark:text-zinc-400",
                      )}>
                        {section.title}
                      </span>
                    </div>
                    <span className={cn(
                      "text-xs text-zinc-400 transition-transform duration-200",
                      isExpanded && "rotate-180",
                    )}>
                      ▼
                    </span>
                  </button>
                  {isExpanded && (
                    <div className="px-4 pb-3 pt-1 border-t border-zinc-100 dark:border-zinc-800">
                      {section.content.length > 0 ? (
                        <div className="space-y-0.5">
                          {section.content.map((l, i) => renderLine(l, i))}
                        </div>
                      ) : (
                        <p className="text-xs text-zinc-400 italic">No details</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-zinc-100 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/50">
        <div className="flex items-center justify-between text-[10px] text-zinc-400">
          <span>{lines.length} lines · {report.length} chars</span>
          <span className="font-mono">Generated by GemmaFinOS AI</span>
        </div>
      </div>
    </div>
  );
}
