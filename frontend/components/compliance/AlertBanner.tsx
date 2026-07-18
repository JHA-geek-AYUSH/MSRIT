'use client';

import { cn } from '@/lib/utils';

interface Props {
  requiresStr: boolean;
  requiresEdd: boolean;
}

export function AlertBanner({ requiresStr, requiresEdd }: Props) {
  if (!requiresStr && !requiresEdd) return null;

  return (
    <div className="flex flex-col sm:flex-row gap-3">
      {requiresStr && (
        <div className={cn(
          "flex-1 group relative overflow-hidden rounded-xl border p-4 transition-all duration-300",
          "border-red-200 bg-gradient-to-br from-red-50 to-red-50/50",
          "dark:border-red-900 dark:from-red-950/40 dark:to-red-950/20"
        )}>
          {/* Decorative line */}
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-red-400 to-red-600 rounded-full" />
          
          <div className="flex items-start gap-3 pl-2">
            <div className="flex-shrink-0 w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/50 flex items-center justify-center">
              <span className="text-lg animate-pulse">🚨</span>
            </div>
            <div>
              <p className="text-sm font-bold text-red-800 dark:text-red-300">STR Filing Required</p>
              <p className="text-xs text-red-600 dark:text-red-400 mt-1 leading-relaxed">
                Suspicious Transaction Report must be filed with <strong>FIU-IND</strong> within{' '}
                <strong>7 working days</strong> under PMLA 2002. Non-compliance may result in
                penalties up to ₹1,00,000.
              </p>
              <div className="mt-2 flex gap-2">
                <span className="inline-flex items-center gap-1 text-[10px] font-medium text-red-700 dark:text-red-300 bg-red-100 dark:bg-red-900/50 px-2 py-0.5 rounded-full">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                  Immediate action
                </span>
                <span className="inline-flex items-center text-[10px] text-red-500 dark:text-red-400">
                  PMLA Section 12
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
      {requiresEdd && (
        <div className={cn(
          "flex-1 group relative overflow-hidden rounded-xl border p-4 transition-all duration-300",
          "border-amber-200 bg-gradient-to-br from-amber-50 to-amber-50/50",
          "dark:border-amber-900 dark:from-amber-950/40 dark:to-amber-950/20"
        )}>
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-amber-400 to-amber-600 rounded-full" />
          
          <div className="flex items-start gap-3 pl-2">
            <div className="flex-shrink-0 w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-900/50 flex items-center justify-center">
              <span className="text-lg">⚠️</span>
            </div>
            <div>
              <p className="text-sm font-bold text-amber-800 dark:text-amber-300">Enhanced Due Diligence Required</p>
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-1 leading-relaxed">
                Customer risk profile requires <strong>Enhanced Due Diligence</strong> as per{' '}
                <strong>RBI KYC Master Direction 2016</strong>, Section 16. Additional documentation
                and senior management approval needed.
              </p>
              <div className="mt-2 flex gap-2">
                <span className="inline-flex items-center gap-1 text-[10px] font-medium text-amber-700 dark:text-amber-300 bg-amber-100 dark:bg-amber-900/50 px-2 py-0.5 rounded-full">
                  Senior management approval
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
