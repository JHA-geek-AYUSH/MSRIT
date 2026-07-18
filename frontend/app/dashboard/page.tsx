"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useUser } from "@clerk/nextjs";
import { Header } from "@/components/layout/Header";
import { getDashboard, reviewApproval } from "@/lib/compliance-api";
import {
  TrendingUp, AlertTriangle, Clock, CheckCircle,
  XCircle, Loader2, RefreshCw, ShieldCheck, ArrowRight
} from "lucide-react";

const TIER_STYLES: Record<string, { cls: string; label: string }> = {
  low:      { cls: "bg-emerald-50 text-emerald-700 border-emerald-200", label: "Low" },
  medium:   { cls: "bg-amber-50 text-amber-700 border-amber-200",       label: "Medium" },
  high:     { cls: "bg-orange-50 text-orange-700 border-orange-200",    label: "High" },
  critical: { cls: "bg-red-50 text-red-700 border-red-200",             label: "Critical" },
};

const ROLE_LABELS: Record<string, string> = {
  finance_analyst:    "Finance Analyst",
  compliance_officer: "Compliance Officer",
  auditor:            "Auditor",
  cfo:                "CFO",
  admin:              "Administrator",
};

function Skeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 animate-pulse">
      <div className="h-36 rounded-2xl bg-stone-200/60 lg:col-span-1" />
      <div className="h-36 rounded-2xl bg-stone-200/60 lg:col-span-2" />
      <div className="h-48 rounded-2xl bg-stone-200/60 lg:col-span-3" />
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useUser();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    getDashboard()
      .then(setData)
      .catch((e) => setError(e.message ?? "Could not load dashboard."))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  return (
    <div className="min-h-screen bg-cream-50">
      <Header />
      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Page header */}
        <div className="flex items-start justify-between mb-8 flex-wrap gap-4">
          <div>
            <p className="font-body text-gold-600 text-xs tracking-widest uppercase font-semibold mb-1">
              {data ? (ROLE_LABELS[data.role] ?? data.role) : "Dashboard"}
            </p>
            <h1 className="font-display text-2xl sm:text-3xl text-brown-900 font-bold">
              Welcome back{user?.firstName ? `, ${user.firstName}` : ""}
            </h1>
            <p className="font-body text-sm text-brown-500 mt-1">Here's your compliance overview.</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={load}
              disabled={loading}
              className="flex items-center gap-1.5 font-body text-xs text-brown-500 hover:text-brown-800 border border-stone-200 bg-white rounded-lg px-3 py-2 transition-colors disabled:opacity-40"
            >
              <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
            </button>
            <Link
              href="/compliance"
              className="flex items-center gap-2 rounded-xl bg-brown-900 text-cream-50 font-body font-semibold text-sm px-4 py-2.5 hover:bg-brown-800 transition-colors"
            >
              <ShieldCheck size={15} /> New Assessment
            </Link>
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-3 rounded-xl bg-red-50 border border-red-200 p-4 mb-6">
            <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
            <p className="font-body text-sm text-red-700">{error}</p>
          </div>
        )}

        {loading ? <Skeleton /> : !data ? null : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

            {/* Penalty exposure KPI */}
            {data.penalty_exposure_summary && (
              <div className="rounded-2xl bg-brown-900 p-6 lg:col-span-1 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-4">
                    <div className="w-7 h-7 rounded-lg bg-cream-50/10 flex items-center justify-center">
                      <TrendingUp size={14} className="text-gold-400" />
                    </div>
                    <p className="font-body text-xs font-semibold text-cream-50/50 uppercase tracking-widest">Penalty Exposure</p>
                  </div>
                  <p className="font-display text-3xl sm:text-4xl text-cream-50 font-bold leading-none">
                    ₹{Math.round(data.penalty_exposure_summary.total_penalty_exposure_inr ?? 0).toLocaleString("en-IN")}
                  </p>
                  <p className="font-body text-xs text-cream-50/40 mt-1">Total across all assessments</p>
                </div>
                <div className="flex gap-5 mt-5 pt-4 border-t border-cream-50/10">
                  <div>
                    <p className="font-body text-xl font-bold text-cream-50">{data.penalty_exposure_summary.assessments_count ?? 0}</p>
                    <p className="font-body text-[10px] text-cream-50/40 uppercase tracking-wide">Assessments</p>
                  </div>
                  <div>
                    <p className="font-body text-xl font-bold text-red-400">{data.penalty_exposure_summary.critical_count ?? 0}</p>
                    <p className="font-body text-[10px] text-cream-50/40 uppercase tracking-wide">Critical</p>
                  </div>
                </div>
              </div>
            )}

            {/* Recent assessments */}
            {data.recent_assessments && (
              <div className="rounded-2xl border border-stone-200 bg-white p-5 lg:col-span-2 shadow-sm">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-stone-100 flex items-center justify-center">
                      <Clock size={13} className="text-brown-400" />
                    </div>
                    <h2 className="font-body text-sm font-semibold text-brown-900">Recent Assessments</h2>
                  </div>
                  <Link href="/compliance/assessments" className="font-body text-xs text-gold-600 hover:text-gold-700 flex items-center gap-1">
                    View all <ArrowRight size={11} />
                  </Link>
                </div>
                {data.recent_assessments.length === 0 ? (
                  <div className="text-center py-6">
                    <ShieldCheck className="w-8 h-8 text-stone-300 mx-auto mb-2" />
                    <p className="font-body text-sm text-brown-500">No assessments yet.</p>
                    <Link href="/compliance" className="font-body text-xs text-gold-600 hover:underline mt-1 block">Run your first assessment →</Link>
                  </div>
                ) : (
                  <div className="space-y-1">
                    {data.recent_assessments.slice(0, 6).map((a: any) => {
                      const tier = TIER_STYLES[a.risk_tier] ?? TIER_STYLES.medium;
                      return (
                        <Link
                          key={a.id}
                          href={`/compliance/report?assessment_id=${a.id}`}
                          className="flex items-center justify-between rounded-xl px-3 py-2.5 hover:bg-stone-50 transition-colors"
                        >
                          <div className="min-w-0">
                            <p className="font-body text-sm text-brown-800 truncate">
                              {new Date(a.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                            </p>
                            <p className="font-body text-xs text-brown-400">
                              ₹{Math.round(a.total_penalty_exposure_inr || 0).toLocaleString("en-IN")} exposure
                            </p>
                          </div>
                          <span className={`font-body text-[11px] font-semibold uppercase border rounded-full px-2.5 py-0.5 shrink-0 ${tier.cls}`}>
                            {tier.label}
                          </span>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Critical findings */}
            {data.critical_findings?.length > 0 && (
              <div className="rounded-2xl border border-red-200 bg-red-50 p-5 lg:col-span-3">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-7 h-7 rounded-lg bg-red-100 flex items-center justify-center">
                    <AlertTriangle size={13} className="text-red-500" />
                  </div>
                  <h2 className="font-body text-sm font-semibold text-red-700">
                    Critical Findings ({data.critical_findings.length})
                  </h2>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {data.critical_findings.map((f: any) => (
                    <Link
                      key={f.id}
                      href={`/compliance/report?assessment_id=${f.id}`}
                      className="flex items-center gap-2 font-body text-sm text-red-700 hover:text-red-900 hover:underline"
                    >
                      <ArrowRight size={12} />
                      Assessment {f.id.slice(0, 8)} — {new Date(f.created_at).toLocaleDateString("en-IN")}
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {/* Pending approvals */}
            {data.pending_approvals && (
              <div className="rounded-2xl border border-stone-200 bg-white p-5 lg:col-span-3 shadow-sm">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-stone-100 flex items-center justify-center">
                      <CheckCircle size={13} className="text-brown-400" />
                    </div>
                    <h2 className="font-body text-sm font-semibold text-brown-900">Pending Approvals</h2>
                  </div>
                  <Link href="/approvals" className="font-body text-xs text-gold-600 hover:text-gold-700 flex items-center gap-1">
                    View all <ArrowRight size={11} />
                  </Link>
                </div>
                {data.pending_approvals.length === 0 ? (
                  <div className="flex items-center gap-2 rounded-xl bg-emerald-50 border border-emerald-200 px-4 py-3">
                    <CheckCircle className="w-4 h-4 text-emerald-500" />
                    <p className="font-body text-sm text-emerald-700">Nothing pending — all clear.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {data.pending_approvals.slice(0, 5).map((a: any) => (
                      <ApprovalRow key={a.id} approval={a} onReviewed={load} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function ApprovalRow({ approval, onReviewed }: { approval: any; onReviewed: () => void }) {
  const [busy, setBusy] = useState(false);

  async function handle(decision: "approve" | "reject") {
    setBusy(true);
    try {
      await reviewApproval(approval.id, decision);
      onReviewed();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center justify-between rounded-xl border border-stone-200 bg-stone-50 px-4 py-3">
      <div className="min-w-0">
        <p className="font-body text-sm font-medium text-brown-900 truncate">{approval.action_type}</p>
        {approval.reason && <p className="font-body text-xs text-brown-500 truncate">{approval.reason}</p>}
      </div>
      <div className="flex items-center gap-2 shrink-0 ml-3">
        {busy ? (
          <Loader2 className="w-4 h-4 text-brown-400 animate-spin" />
        ) : (
          <>
            <button
              onClick={() => handle("approve")}
              className="flex items-center gap-1 font-body text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full px-3 py-1.5 hover:bg-emerald-100 transition-colors"
            >
              <CheckCircle size={11} /> Approve
            </button>
            <button
              onClick={() => handle("reject")}
              className="flex items-center gap-1 font-body text-xs font-semibold bg-red-50 text-red-700 border border-red-200 rounded-full px-3 py-1.5 hover:bg-red-100 transition-colors"
            >
              <XCircle size={11} /> Reject
            </button>
          </>
        )}
      </div>
    </div>
  );
}
