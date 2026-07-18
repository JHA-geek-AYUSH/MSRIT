'use client';

import { cn } from '@/lib/utils';

type Level = 'high' | 'medium' | 'low';

const styles: Record<Level, string> = {
  high:   'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-400 dark:border-red-800',
  medium: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-800',
  low:    'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-800',
};

const labels: Record<Level, string> = {
  high:   'High Risk',
  medium: 'Medium Risk',
  low:    'Low Risk',
};

const dotStyles: Record<Level, string> = {
  high:   'bg-red-500 dark:bg-red-400',
  medium: 'bg-amber-500 dark:bg-amber-400',
  low:    'bg-emerald-500 dark:bg-emerald-400',
};

interface RiskBadgeProps {
  level: Level;
  className?: string;
  size?: 'sm' | 'md';
  animated?: boolean;
}

export function RiskBadge({ level, className, size = 'sm', animated = true }: RiskBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border font-semibold transition-all duration-200',
        size === 'sm' ? 'px-2.5 py-0.5 text-[11px]' : 'px-3.5 py-1 text-xs',
        styles[level],
        animated && 'hover:scale-105',
        className,
      )}
    >
      <span className={cn(
        'w-1.5 h-1.5 rounded-full',
        dotStyles[level],
        animated && 'animate-pulse',
      )} />
      {labels[level]}
    </span>
  );
}
