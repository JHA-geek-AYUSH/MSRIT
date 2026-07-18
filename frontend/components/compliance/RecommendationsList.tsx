'use client';

import { cn } from '@/lib/utils';

interface Props {
  recommendations: string[];
}

const PRIORITY_CONFIG = [
  { icon: '🚨', label: 'Critical', color: 'text-red-600', bar: 'bg-red-500' },
  { icon: '⚠️', label: 'Urgent', color: 'text-orange-500', bar: 'bg-orange-400' },
  { icon: '📋', label: 'High', color: 'text-amber-600', bar: 'bg-amber-400' },
  { icon: '📝', label: 'Medium', color: 'text-blue-600', bar: 'bg-blue-400' },
  { icon: '✅', label: 'Low', color: 'text-emerald-600', bar: 'bg-emerald-400' },
];

export function RecommendationsList({ recommendations }: Props) {
  if (!recommendations.length) return null;

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-zinc-100 dark:border-zinc-800">
        <h2 className="font-semibold text-sm text-zinc-800 dark:text-zinc-200 flex items-center gap-2">
          <span>📋</span>
          Recommended Actions
          <span className="ml-auto text-[10px] text-zinc-400 font-normal">{recommendations.length} items</span>
        </h2>
      </div>
      <ol className="divide-y divide-zinc-100 dark:divide-zinc-800">
        {recommendations.slice(0, 8).map((rec, i) => {
          const config = PRIORITY_CONFIG[Math.min(i, PRIORITY_CONFIG.length - 1)];
          return (
            <li
              key={i}
              className="group flex items-start gap-3 px-5 py-3 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors duration-150"
            >
              {/* Priority bar */}
              <div className={cn("w-0.5 h-full min-h-[2.5rem] rounded-full mt-0.5 shrink-0", config.bar)} />
              
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm">{config.icon}</span>
                  <span className={cn("text-[10px] font-semibold uppercase tracking-wide", config.color)}>
                    {config.label}
                  </span>
                </div>
                <p className="text-sm text-zinc-700 dark:text-zinc-300 mt-0.5 leading-relaxed">{rec}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
