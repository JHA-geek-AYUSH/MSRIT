"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { generateAuditReport } from "@/lib/compliance-api";
import {
  Loader2, AlertTriangle, ClipboardList,
  Building2, TrendingUp, Scale, Wrench, FileText
} from "lucide-react";

function SectionCard({
  icon: Icon, title, children
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-7 h-7 rounded-lg bg-stone-100 flex items-center justify-center">
          <Icon size={13} className="text-brown-400" />
        </div>
        <h2 className="font-body text-sm font-semibold text-brown-900">{title}</h2>
      </div>
      {children}
    </div>
  );
}

const SEVERITY_BADGE: Record<string, string> = {
  low:      "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium:   "bg-amber-50 text-amber-700 border-amber-200",
  high:     "bg-orange-50 text-orange-700 border-orange-200",
  critical: "bg-red-50 text-red-700 border-red-200",
};

const PRIORITY_BADGE: Record<string, string> = {
  HIGH:   "bg-red-50 text-red-700 border-red-200",
  MEDIUM: "bg-amber-50 text-amber-700 border-amber-200",
  LOW:    "bg-stone-100 text-stone-600 border-stone-200",
};

export default function ReportPage() {
  const params = useSearchParams();
  const assessmentId = params.get("assessment_id");
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!assessmentId) return;
    setLoading(true);
    generateAuditReport({ assessment_id: assessmentId })
      .then(setReport)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [assessmentId]);

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <p className="font-body text-gold-600 text-xs tracking-widest uppercase font-semibold mb-1">Audit Report</p>
        <h1 className="font-display text-2xl sm:text-3xl text-brown-900 font-bold mb-1">Compliance Audit Report</h1>
      </div>

      {!assessmentId && (
        <div className="rounded-2xl border border-dashed border-stone-200 p-10 text-center">
          <ClipboardList className="w-8 h-8 text-stone-300 mx-auto mb-3" />
          <p className="font-body text-sm text-brown-500">No assessment selected.</p>
          <p className="font-body text-xs text-brown-400 mt-1">Open this page from an assessment history entry.</p>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-3 rounded-xl bg-stone-50 border border-stone-200 p-4">
          <Loader2 className="w-4 h-4 text-gold-500 animate-spin" />
          <p className="font-body text-sm text-brown-700">Generating report with Gemma…</p>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-3 rounded-xl bg-red-50 border border-red-200 p-4">
          <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
          <p className="font-body text-sm text-red-700">{error}</p>
        </div>
      )}

      {report && (
        <div className="space-y-4">
          {/* Executive summary */}
          <div className="rounded-2xl border border-brown-900/10 bg-brown-900 p-6 shadow-lg">
            <p className="font-body text-xs font-semibold uppercase tracking-widest text-cream-50/40 mb-2">Executive Summary</p>
            <p className="font-body text-sm text-cream-50/90 leading-relaxed">{report.gemma_summary}</p>
          </div>

          {/* Entity */}
          <SectionCard icon={Building2} title="Entity">
            <p className="font-body text-sm font-semibold text-brown-900">{report.section_1_entity_summary?.business_name}</p>
            <p className="font-body text-xs text-brown-500 mt-0.5">
              {report.section_1_entity_summary?.sector} &middot; Assessed {report.section_1_entity_summary?.assessment_date}
            </p>
          </SectionCard>

          {/* Risk assessment */}
          <SectionCard icon={TrendingUp} title="Risk Assessment">
            <div className="flex items-center gap-3 mb-3">
              <span className={`font-body text-xs font-semibold uppercase border rounded-full px-2.5 py-0.5 ${SEVERITY_BADGE[report.section_2_risk_assessment?.risk_tier?.toLowerCase()] ?? "bg-stone-100 text-stone-600 border-stone-200"}`}>
                {report.section_2_risk_assessment?.risk_tier}
              </span>
              <span className="font-body text-sm text-brown-600">{report.section_2_risk_assessment?.confidence_pct}% confidence</span>
            </div>
            {report.section_2_risk_assessment?.top_risk_drivers?.length > 0 && (
              <ul className="space-y-1.5">
                {report.section_2_risk_assessment.top_risk_drivers.map((d: any) => (
                  <li key={d.rule_code} className="flex items-center gap-2 font-body text-xs text-brown-600">
                    <span className="w-1.5 h-1.5 rounded-full bg-gold-400 shrink-0" />
                    <span className="font-semibold text-brown-800">{d.rule_code}</span> — {d.rule_name}
                    {d.contribution_pct && <span className="ml-auto text-brown-400">{d.contribution_pct}%</span>}
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          {/* Findings */}
          <SectionCard icon={Scale} title="Compliance Findings">
            <div className="space-y-2">
              {report.section_3_compliance_findings?.map((f: any) => (
                <div key={f.rule_code} className="rounded-xl border border-stone-200 bg-stone-50 p-3.5">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className={`font-body text-[10px] font-semibold uppercase border rounded-full px-2 py-0.5 ${SEVERITY_BADGE[f.severity?.toLowerCase()] ?? "bg-stone-100 text-stone-600 border-stone-200"}`}>
                      {f.severity}
                    </span>
                    <span className="font-body text-sm font-semibold text-brown-900">{f.rule_code} — {f.rule_name}</span>
                  </div>
                  <p className="font-body text-sm text-brown-600 leading-relaxed">{f.plain_english_finding}</p>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Penalty */}
          <SectionCard icon={TrendingUp} title="Penalty Exposure">
            <p className="font-display text-3xl font-bold text-brown-900">
              ₹{Math.round(report.section_4_penalty_exposure?.total_estimated_fine_inr || 0).toLocaleString("en-IN")}
            </p>
            <p className="font-body text-sm text-brown-600 mt-1">
              Urgency: <span className="font-semibold text-brown-800">{report.section_4_penalty_exposure?.urgency_tier}</span>
            </p>
            {report.section_4_penalty_exposure?.imprisonment_risk && (
              <div className="flex items-center gap-2 mt-3 rounded-xl bg-red-50 border border-red-200 px-3 py-2">
                <AlertTriangle className="w-3.5 h-3.5 text-red-500 shrink-0" />
                <p className="font-body text-xs text-red-700">Imprisonment risk present</p>
              </div>
            )}
          </SectionCard>

          {/* Actions */}
          <SectionCard icon={Wrench} title="Recommended Actions">
            <ol className="space-y-2">
              {report.section_5_recommended_actions?.map((a: any, i: number) => (
                <li key={i} className="flex items-start gap-3">
                  <span className={`font-body text-[10px] font-semibold uppercase border rounded-full px-2 py-0.5 shrink-0 mt-0.5 ${PRIORITY_BADGE[a.priority] ?? "bg-stone-100 text-stone-600 border-stone-200"}`}>
                    {a.priority}
                  </span>
                  <p className="font-body text-sm text-brown-700 leading-relaxed">{a.action}</p>
                </li>
              ))}
            </ol>
          </SectionCard>
        </div>
      )}
    </div>
  );
}
