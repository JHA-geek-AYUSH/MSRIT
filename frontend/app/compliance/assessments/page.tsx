"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getAssessmentHistory } from "@/lib/compliance-api";
import { ListSkeleton } from "@/components/ui/loading-state";

const TIER_STYLES: Record<string, string> = {
  low: "bg-olive-400/15 text-olive-400 border-olive-400/40",
  medium: "bg-gold-500/15 text-gold-500 border-gold-500/40",
  high: "bg-error-500/10 text-error-500 border-error-500/40",
  critical: "bg-error-500 text-cream-50 border-error-500",
};

/**
 * Persisted assessment history from the real 3-stage pipeline
 * (POST /v1/compliance/assess -> compliance_assessments table).
 * Distinct from /compliance/history, which is a sessionStorage-only log of the
 * older LLM-reasoning /compliance/triage flow.
 */
export default function AssessmentsHistoryPage() {
  const [assessments, setAssessments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    getAssessmentHistory()
      .then((res) => {
        setAssessments(res.assessments || []);
        if (res.note) setNote(res.note);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-3xl mx-auto">
        <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-100 mb-6">All Assessments</h1>

        {note && (
          <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 rounded-xl p-4 mb-6 text-sm text-amber-800 dark:text-amber-300">
            {note} — run <code className="text-xs bg-amber-100 dark:bg-amber-900/50 px-1 py-0.5 rounded">alembic upgrade head</code> to enable persistence.
          </div>
        )}

        {loading ? (
          <ListSkeleton rows={4} />
        ) : assessments.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No assessments yet.{' '}
            <Link href="/compliance" className="text-blue-500 hover:text-blue-700 underline">Run one from the triage page.</Link>
          </p>
        ) : (
          <div className="space-y-2">
            {assessments.map((a) => (
              <Link
                key={a.id}
                href={`/compliance/report?assessment_id=${a.id}`}
                className="block rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-4 hover:border-blue-300 dark:hover:border-blue-700 transition-colors shadow-sm"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-zinc-500">{new Date(a.created_at).toLocaleString("en-IN")}</p>
                    <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200 mt-1">₹{Math.round(a.total_penalty_exposure_inr || 0).toLocaleString("en-IN")} exposure</p>
                  </div>
                  <span className={`text-[10px] uppercase font-medium border rounded-full px-2.5 py-1 ${TIER_STYLES[a.risk_tier] || "bg-zinc-200 text-zinc-700"}`}>
                    {a.risk_tier?.toUpperCase()} · {a.confidence_pct}%
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
    </div>
  );
}
