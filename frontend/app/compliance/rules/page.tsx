"use client";

import { useEffect, useState } from "react";
import { getRules, type RuleSummary } from "@/lib/compliance-api";
import { Search, AlertTriangle, BookMarked } from "lucide-react";

function Skeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-24 rounded-xl bg-stone-200/60 animate-pulse" />
      ))}
    </div>
  );
}

const SEVERITY_BADGE: Record<string, string> = {
  low:      "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium:   "bg-amber-50 text-amber-700 border-amber-200",
  high:     "bg-orange-50 text-orange-700 border-orange-200",
  critical: "bg-red-50 text-red-700 border-red-200",
};

const FRAMEWORKS = ["", "PMLA", "RBI_KYC", "GST", "FEMA", "INCOME_TAX", "COMPANIES_ACT"];
const SEVERITIES  = ["", "critical", "high", "medium", "low"];

export default function RulesPage() {
  const [rules, setRules]       = useState<RuleSummary[]>([]);
  const [framework, setFramework] = useState("");
  const [severity, setSeverity]   = useState("");
  const [loading, setLoading]     = useState(true);
  const [search, setSearch]       = useState("");

  useEffect(() => {
    setLoading(true);
    getRules({ framework: framework || undefined, severity: severity || undefined })
      .then((res) => setRules(res.rules ?? []))
      .finally(() => setLoading(false));
  }, [framework, severity]);

  const filtered = rules.filter(
    (r) =>
      r.name.toLowerCase().includes(search.toLowerCase()) ||
      r.code.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <p className="font-body text-gold-600 text-xs tracking-widest uppercase font-semibold mb-1">Rule Catalogue</p>
        <h1 className="font-display text-2xl sm:text-3xl text-brown-900 font-bold mb-1">
          40 Compliance Rules
        </h1>
        <p className="font-body text-sm text-brown-600 leading-relaxed">
          Rules across 6 Indian regulatory frameworks: PMLA, FEMA, RBI KYC, GST, Income Tax, Companies Act.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-brown-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or code…"
            className="w-full rounded-xl border border-stone-200 bg-white pl-9 pr-4 py-2.5 font-body text-sm text-brown-900 placeholder:text-brown-300 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400 transition-colors shadow-sm"
          />
        </div>
        <select
          value={framework}
          onChange={(e) => setFramework(e.target.value)}
          className="rounded-xl border border-stone-200 bg-white px-3.5 py-2.5 font-body text-sm text-brown-900 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400 transition-colors shadow-sm"
        >
          {FRAMEWORKS.map((f) => (
            <option key={f} value={f}>{f ? f.replace(/_/g, " ") : "All frameworks"}</option>
          ))}
        </select>
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="rounded-xl border border-stone-200 bg-white px-3.5 py-2.5 font-body text-sm text-brown-900 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400 transition-colors shadow-sm"
        >
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{s ? s.charAt(0).toUpperCase() + s.slice(1) : "All severities"}</option>
          ))}
        </select>
      </div>

      {/* List */}
      {loading ? (
        <Skeleton />
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-stone-200 p-10 text-center">
          <BookMarked className="w-8 h-8 text-stone-300 mx-auto mb-3" />
          <p className="font-body text-sm text-brown-500">No rules match your filters.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((r) => (
            <div
              key={r.code}
              className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm hover:border-stone-300 hover:shadow-md transition-all"
            >
              <div className="flex items-start justify-between gap-4 mb-2">
                <div className="min-w-0">
                  <p className="font-body text-sm font-semibold text-brown-900">
                    {r.code} &mdash; {r.name}
                  </p>
                  <p className="font-body text-[10px] font-semibold uppercase tracking-widest text-gold-600 mt-0.5">
                    {r.framework.replace(/_/g, " ")}
                  </p>
                </div>
                <span className={`font-body text-[11px] font-semibold uppercase border rounded-full px-2.5 py-0.5 shrink-0 ${SEVERITY_BADGE[r.severity] ?? "bg-stone-100 text-stone-600 border-stone-200"}`}>
                  {r.severity}
                </span>
              </div>
              <p className="font-body text-sm text-brown-600 leading-relaxed">{r.description}</p>
              <div className="flex items-center gap-4 mt-2.5 pt-2.5 border-t border-stone-100">
                <span className="font-body text-xs text-brown-400">
                  Max penalty ₹{(r.max_penalty_inr ?? 0).toLocaleString("en-IN")}
                </span>
                {r.imprisonment_risk && (
                  <span className="flex items-center gap-1 font-body text-xs text-red-600">
                    <AlertTriangle size={11} /> Imprisonment risk
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
