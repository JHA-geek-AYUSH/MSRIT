"use client";

import { useEffect, useState } from "react";
import { Header } from "@/components/layout/Header";
import { getPendingApprovals, reviewApproval } from "@/lib/compliance-api";
import {
  AlertTriangle, CheckCircle, XCircle, Loader2,
  RefreshCw, ShieldCheck
} from "lucide-react";

const RISK_BADGE: Record<string, { cls: string; label: string }> = {
  low:      { cls: "bg-emerald-50 text-emerald-700 border-emerald-200",  label: "Low" },
  medium:   { cls: "bg-amber-50 text-amber-700 border-amber-200",        label: "Medium" },
  high:     { cls: "bg-orange-50 text-orange-700 border-orange-200",     label: "High" },
  critical: { cls: "bg-red-50 text-red-700 border-red-200",              label: "Critical" },
};

function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-20 rounded-xl bg-stone-200/60 animate-pulse" />
      ))}
    </div>
  );
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    getPendingApprovals()
      .then((res) => setApprovals(res.approvals ?? []))
      .catch((e) => setError(e.message ?? "Could not load approvals."))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleReview(id: string, decision: "approve" | "reject") {
    try {
      await reviewApproval(id, decision);
      load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="min-h-screen bg-cream-50">
      <Header />
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Page header */}
        <div className="mb-8">
          <p className="font-body text-gold-600 text-xs tracking-widest uppercase font-semibold mb-1">Human-in-the-loop</p>
          <h1 className="font-display text-2xl sm:text-3xl text-brown-900 font-bold mb-1">Pending Approvals</h1>
          <p className="font-body text-sm text-brown-600 max-w-xl leading-relaxed">
            High-risk actions — external connector writes, critical-severity escalations — are staged here
            instead of executing automatically. Requires a Compliance Officer, CFO, or Auditor to review.
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-start gap-3 rounded-xl bg-red-50 border border-red-200 p-4 mb-6">
            <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
            <p className="font-body text-sm text-red-700">{error}</p>
            <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600 font-body text-lg leading-none">&times;</button>
          </div>
        )}

        {/* Toolbar */}
        <div className="flex items-center justify-between mb-4">
          <p className="font-body text-sm text-brown-600">
            {!loading && `${approvals.length} pending`}
          </p>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 font-body text-xs text-brown-500 hover:text-brown-800 border border-stone-200 bg-white rounded-lg px-3 py-2 transition-colors disabled:opacity-40"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>

        {/* Content */}
        {loading ? (
          <Skeleton rows={3} />
        ) : approvals.length === 0 ? (
          <div className="rounded-2xl border border-stone-200 bg-white p-12 text-center shadow-sm">
            <div className="w-12 h-12 rounded-xl bg-emerald-50 flex items-center justify-center mx-auto mb-4">
              <ShieldCheck className="w-6 h-6 text-emerald-500" />
            </div>
            <p className="font-body text-sm font-semibold text-brown-800">All clear — nothing pending</p>
            <p className="font-body text-xs text-brown-400 mt-1">No actions awaiting approval right now.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {approvals.map((a) => {
              const badge = RISK_BADGE[a.risk_level] ?? RISK_BADGE.medium;
              return (
                <div key={a.id} className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm hover:border-stone-300 transition-all">
                  <div className="flex items-start justify-between gap-4 mb-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-body text-sm font-semibold text-brown-900">{a.action_type}</p>
                        {a.connector && (
                          <span className="font-body text-[10px] uppercase tracking-wide font-semibold bg-gold-500/10 text-gold-600 border border-gold-500/20 rounded-full px-2 py-0.5">
                            {a.connector}
                          </span>
                        )}
                      </div>
                      {a.reason && (
                        <p className="font-body text-sm text-brown-600 mt-1 leading-relaxed">{a.reason}</p>
                      )}
                    </div>
                    <span className={`font-body text-[11px] font-semibold uppercase border rounded-full px-2.5 py-0.5 shrink-0 ${badge.cls}`}>
                      {badge.label}
                    </span>
                  </div>

                  {a.payload && (
                    <pre className="font-mono text-xs text-brown-500 bg-stone-50 border border-stone-200 rounded-xl p-3 overflow-x-auto mb-3 leading-relaxed">
                      {JSON.stringify(a.payload, null, 2)}
                    </pre>
                  )}

                  <div className="flex items-center gap-2">
                    <ApproveButton id={a.id} decision="approve" onReviewed={handleReview} />
                    <ApproveButton id={a.id} decision="reject" onReviewed={handleReview} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}

function ApproveButton({
  id, decision, onReviewed
}: {
  id: string;
  decision: "approve" | "reject";
  onReviewed: (id: string, d: "approve" | "reject") => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);

  async function handle() {
    setBusy(true);
    try { await onReviewed(id, decision); }
    finally { setBusy(false); }
  }

  const isApprove = decision === "approve";

  return (
    <button
      onClick={handle}
      disabled={busy}
      className={`flex items-center gap-1.5 font-body text-xs font-semibold rounded-xl px-4 py-2 border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
        isApprove
          ? "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100"
          : "bg-red-50 text-red-700 border-red-200 hover:bg-red-100"
      }`}
    >
      {busy ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : isApprove ? (
        <CheckCircle size={13} />
      ) : (
        <XCircle size={13} />
      )}
      {isApprove ? "Approve" : "Reject"}
    </button>
  );
}
