'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import { RiskBadge } from '@/components/compliance/RiskBadge';
import { getTriageHistory, getTriageRun, type TriageHistoryEntry } from '@/lib/compliance-api';
import { DetailDrawer, DrawerSection, FactGrid, FlagList } from '@/components/compliance/DetailDrawer';
import { ChevronRight } from 'lucide-react';

export default function ComplianceHistoryPage() {
  const [history, setHistory] = useState<TriageHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Detail drawer — full triage run (domains, recommendations, report) for one past run
  const [selectedRun, setSelectedRun] = useState<TriageHistoryEntry | null>(null);
  const [runDetail, setRunDetail] = useState<Record<string, any> | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);

  function openRun(entry: TriageHistoryEntry) {
    setSelectedRun(entry);
    setRunDetail(null);
    setDrawerLoading(true);
    getTriageRun(entry.run_id)
      .then((res) => setRunDetail(res))
      .catch(() => setRunDetail(null))
      .finally(() => setDrawerLoading(false));
  }

  useEffect(() => {
    getTriageHistory()
      .then(({ runs }) => setHistory(runs))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="max-w-3xl mx-auto">
        <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-100 mb-6">Triage History</h1>
        {history.length === 0 ? (
          <div className="text-center py-20 text-zinc-400">
            <div className="text-5xl mb-4">📋</div>
            <p className="text-sm">No triage runs yet.</p>
            <p className="text-xs mt-2 text-zinc-300">
              Completed and failed runs are retained in your compliance workspace.
            </p>
            <Link
              href="/compliance"
              className="inline-block mt-6 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-6 py-2.5 transition-colors"
            >
              Run your first triage
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {history.map((entry) => (
              <button
                key={entry.run_id}
                onClick={() => openRun(entry)}
                className="w-full rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-4 flex items-center gap-4 shadow-sm hover:border-blue-300 dark:hover:border-blue-700 transition-colors text-left"
              >
                <RiskBadge level={entry.overall_rating || 'low'} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-700 dark:text-zinc-300 truncate">
                    {entry.description_preview}
                  </p>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    {new Date(entry.created_at).toLocaleString()} · Run #{entry.run_id.slice(0, 8)}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {entry.requires_str && (
                    <span className="text-xs rounded-full bg-red-100 text-red-700 border border-red-300 px-2 py-0.5 font-semibold">
                      STR
                    </span>
                  )}
                  {entry.requires_edd && (
                    <span className="text-xs rounded-full bg-amber-100 text-amber-700 border border-amber-300 px-2 py-0.5 font-semibold">
                      EDD
                    </span>
                  )}
                  <ChevronRight className="w-3.5 h-3.5 text-zinc-300" />
                </div>
              </button>
            ))}
          </div>
        )}
        {error && <p className="mt-4 text-sm text-red-600">Unable to load triage history: {error}</p>}

      {/* Run detail drawer */}
      <DetailDrawer
        isOpen={selectedRun !== null}
        onClose={() => setSelectedRun(null)}
        title={`Run #${selectedRun?.run_id.slice(0, 8) ?? ""}`}
        subtitle={selectedRun ? new Date(selectedRun.created_at).toLocaleString() : undefined}
        riskTier={selectedRun?.overall_rating}
        loading={drawerLoading}
      >
        {selectedRun && runDetail && (
          <>
            <DrawerSection label="Description">
              <p className="font-body text-xs text-brown-600 leading-relaxed bg-white border border-stone-200 rounded-xl px-3 py-2.5">
                {selectedRun.description_preview}
              </p>
            </DrawerSection>

            <DrawerSection label="Domain Scorecard">
              <FlagList
                tone="stone"
                empty="No domain-level findings."
                items={(runDetail.result?.domains ?? []).map((d: any) => ({
                  title: `${d.name} · ${String(d.rating).toUpperCase()} (${Math.round((d.confidence || 0) * 100)}% confidence)`,
                  detail: d.summary,
                }))}
              />
            </DrawerSection>

            <DrawerSection label="Recommendations">
              <FlagList
                tone="amber"
                empty="No recommendations generated."
                items={(runDetail.result?.recommendations ?? []).map((r: string) => ({ title: r }))}
              />
            </DrawerSection>

            <DrawerSection label="Flags">
              <FactGrid
                items={[
                  { label: "STR Required", value: selectedRun.requires_str ? "Yes" : "No" },
                  { label: "EDD Required", value: selectedRun.requires_edd ? "Yes" : "No" },
                  { label: "Mode", value: runDetail.mode },
                  { label: "Status", value: runDetail.status },
                ]}
              />
            </DrawerSection>
          </>
        )}
      </DetailDrawer>
    </div>
  );
}
