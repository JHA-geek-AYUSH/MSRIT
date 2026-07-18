'use client';

import { cn } from '@/lib/utils';
import { RiskBadge } from './RiskBadge';
import type { RiskDomain } from '@/lib/compliance-api';

const DOMAIN_META: Record<string, { icon: string; gradient: string }> = {
  Transaction:      { icon: '💳', gradient: 'from-blue-500/10 to-blue-500/5' },
  Onboarding:       { icon: '🪪', gradient: 'from-violet-500/10 to-violet-500/5' },
  Regulatory:       { icon: '⚖️', gradient: 'from-amber-500/10 to-amber-500/5' },
  'Financial Risk': { icon: '📊', gradient: 'from-rose-500/10 to-rose-500/5' },
  Report:           { icon: '📄', gradient: 'from-teal-500/10 to-teal-500/5' },
};

function ConfidenceBar({ value, rating }: { value: number; rating: string }) {
  const pct = Math.round(value * 100);
  const colorMap: Record<string, string> = {
    high: 'bg-gradient-to-r from-red-400 to-red-500',
    medium: 'bg-gradient-to-r from-amber-400 to-amber-500',
    low: 'bg-gradient-to-r from-emerald-400 to-emerald-500',
  };
  const bgMap: Record<string, string> = {
    high: 'bg-red-100 dark:bg-red-950/50',
    medium: 'bg-amber-100 dark:bg-amber-950/50',
    low: 'bg-emerald-100 dark:bg-emerald-950/50',
  };

  return (
    <div className="mt-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-zinc-500 dark:text-zinc-400 font-medium">Confidence</span>
        <span className="text-[10px] text-zinc-400 dark:text-zinc-500 font-mono">{pct}%</span>
      </div>
      <div className={cn("h-2 rounded-full overflow-hidden", bgMap[rating] || 'bg-zinc-100')}>
        <div
          className={cn("h-full rounded-full transition-all duration-1000 ease-out", colorMap[rating] || 'bg-blue-500')}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function RiskScorecard({ domains }: { domains: RiskDomain[] }) {
  if (!domains.length) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
      {domains.map((d, idx) => {
        const meta = DOMAIN_META[d.name] || { icon: '🔍', gradient: 'from-zinc-500/10 to-zinc-500/5' };
        return (
          <div
            key={d.name}
            className={cn(
              "group relative rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-4",
              "shadow-sm hover:shadow-md transition-all duration-300",
              "hover:-translate-y-0.5",
              "overflow-hidden",
            )}
            style={{ animationDelay: `${idx * 80}ms` }}
          >
            {/* Gradient overlay */}
            <div className={cn(
              "absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-gradient-to-br",
              meta.gradient,
            )} />
            
            {/* Content */}
            <div className="relative z-10">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl">{meta.icon}</span>
                  <span className="font-semibold text-sm text-zinc-800 dark:text-zinc-100">{d.name}</span>
                </div>
              </div>

              <RiskBadge level={d.rating} size="md" animated={false} />

              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2.5 line-clamp-3 leading-relaxed">
                {d.summary || '—'}
              </p>

              <ConfidenceBar value={d.confidence} rating={d.rating} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
