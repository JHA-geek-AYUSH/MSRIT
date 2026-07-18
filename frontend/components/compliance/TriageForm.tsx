'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { TriageMode } from '@/lib/compliance-api';

const MODES: { value: TriageMode; label: string; desc: string; icon: string; color: string }[] = [
  { value: 'full',           label: 'Full Triage',       desc: 'All compliance modules',     icon: '🔄', color: 'from-blue-500 to-blue-600' },
  { value: 'transaction',    label: 'Transaction',        desc: 'AML / anomaly detection',    icon: '💳', color: 'from-violet-500 to-violet-600' },
  { value: 'onboarding',     label: 'KYC/Onboarding',    desc: 'Document & PEP checks',      icon: '🪪', color: 'from-emerald-500 to-emerald-600' },
  { value: 'regulatory',     label: 'Regulatory',         desc: 'Framework & breach mapping', icon: '⚖️', color: 'from-amber-500 to-amber-600' },
  { value: 'financial_risk', label: 'Financial Risk',   desc: 'Credit, market, liquidity',   icon: '📊', color: 'from-rose-500 to-rose-600' },
];

interface Props {
  onSubmit: (description: string, mode: TriageMode) => void;
  loading: boolean;
}

export function TriageForm({ onSubmit, loading }: Props) {
  const [description, setDescription] = useState('');
  const [mode, setMode] = useState<TriageMode>('full');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (description.trim().length < 10) return;
    onSubmit(description.trim(), mode);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Mode selector */}
      <div>
        <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-3">
          Triage Mode
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
          {MODES.map((m) => {
            const isActive = mode === m.value;
            return (
              <button
                key={m.value}
                type="button"
                onClick={() => setMode(m.value)}
                disabled={loading}
                className={cn(
                  "relative rounded-xl border-2 px-3.5 py-3 text-left transition-all duration-200",
                  "hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed",
                  isActive
                    ? cn("border-transparent shadow-lg scale-[1.02]", getBorderGradient(m.value))
                    : "border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:border-zinc-300 dark:hover:border-zinc-600 hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                )}
              >
                {isActive && (
                  <div className={cn(
                    "absolute inset-0 rounded-xl opacity-10 bg-gradient-to-br",
                    m.color
                  )} />
                )}
                <div className="relative flex items-center gap-2.5">
                  <span className="text-lg">{m.icon}</span>
                  <div>
                    <div className={cn(
                      "text-xs font-semibold",
                      isActive ? "text-zinc-900 dark:text-zinc-100" : "text-zinc-700 dark:text-zinc-300"
                    )}>
                      {m.label}
                    </div>
                    <div className={cn(
                      "text-[10px] mt-0.5",
                      isActive ? "text-zinc-500" : "text-zinc-400 dark:text-zinc-500"
                    )}>
                      {m.desc}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Description textarea */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Transaction / Onboarding / Financial Record Description
          </label>
          <span className={cn(
            "text-[10px] font-mono",
            description.length < 10 ? "text-red-400" : "text-zinc-400"
          )}>
            {description.length} chars
          </span>
        </div>
        <div className="relative">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={6}
            placeholder={`Paste or describe the financial record here.

Examples:
• "Customer transferred ₹9.8L three times in 5 days to three different accounts in different cities..."
• "New corporate client requesting account opening. Directors include a PEP with government connections..."
• "Loan application from SME with ₹2.4Cr turnover showing 60-day overdue invoices..."`}
            className={cn(
              "w-full rounded-xl border-2 bg-white dark:bg-zinc-900 text-sm text-zinc-800 dark:text-zinc-100 p-3.5",
              "resize-none transition-all duration-200",
              "focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500",
              "placeholder:text-zinc-400 dark:placeholder:text-zinc-600",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              description.length >= 10
                ? "border-zinc-200 dark:border-zinc-700"
                : description.length > 0
                  ? "border-red-200 dark:border-red-900"
                  : "border-zinc-200 dark:border-zinc-700"
            )}
            disabled={loading}
          />
          {description.length > 0 && description.length < 10 && (
            <p className="absolute -bottom-5 left-0 text-[10px] text-red-400">
              Minimum 10 characters required
            </p>
          )}
        </div>
      </div>

      <button
        type="submit"
        disabled={loading || description.trim().length < 10}
        className={cn(
          "w-full rounded-xl font-semibold py-3 text-sm transition-all duration-200",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          "bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800",
          "text-white shadow-md hover:shadow-lg",
          "active:scale-[0.99]",
          !loading && "hover:-translate-y-0.5"
        )}
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2.5">
            <span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
            <span>Running compliance triage...</span>
          </span>
        ) : (
          <span className="flex items-center justify-center gap-2">
            <span>⚡</span>
            Run Compliance Triage
          </span>
        )}
      </button>
    </form>
  );
}

function getBorderGradient(mode: TriageMode): string {
  switch (mode) {
    case 'full': return 'border-blue-500';
    case 'transaction': return 'border-violet-500';
    case 'onboarding': return 'border-emerald-500';
    case 'regulatory': return 'border-amber-500';
    case 'financial_risk': return 'border-rose-500';
  }
}
