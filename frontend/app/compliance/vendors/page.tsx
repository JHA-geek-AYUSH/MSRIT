"use client";

import { useEffect, useRef, useState } from "react";
import { onboardVendor, listVendorCases, getAuditTrail } from "@/lib/compliance-api";
import { DetailDrawer, DrawerSection, FactGrid, FlagList, AuditTimeline } from "@/components/compliance/DetailDrawer";
import {
  Loader2, AlertTriangle, RefreshCw, Building2,
  ShieldAlert, CheckCircle, FileCheck, Upload, ChevronRight,
} from "lucide-react";

function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-14 rounded-xl bg-stone-200/60 animate-pulse" />
      ))}
    </div>
  );
}

const KYC_BADGE: Record<string, { label: string; cls: string }> = {
  approved: { label: "Approved", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  in_review: { label: "In Review", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  escalated: { label: "Escalated", cls: "bg-red-50 text-red-700 border-red-200" },
};

const SECTORS = ["Trading", "Manufacturing", "IT Services", "NBFC", "Import/Export", "Real Estate", "Retail", "Healthcare", "Education"];

export default function VendorsPage() {
  const [name, setName] = useState("");
  const [gstin, setGstin] = useState("");
  const [pan, setPan] = useState("");
  const [sector, setSector] = useState("Trading");
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [cases, setCases] = useState<Record<string, any>[]>([]);
  const [loading, setLoading] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Detail drawer — shows missing docs / PEP / UBO findings + linked audit trail for one case
  const [selectedCase, setSelectedCase] = useState<Record<string, any> | null>(null);
  const [caseAuditEntries, setCaseAuditEntries] = useState<Record<string, any>[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);

  function openCase(c: Record<string, any>) {
    setSelectedCase(c);
    setDrawerLoading(true);
    getAuditTrail({ entity_type: "vendor_onboarding_case", entity_id: c.case_id })
      .then((res) => setCaseAuditEntries(res.entries ?? []))
      .catch(() => setCaseAuditEntries([]))
      .finally(() => setDrawerLoading(false));
  }

  function load() {
    setLoading(true);
    setError(null);
    listVendorCases()
      .then((res) => setCases(res.cases ?? []))
      .catch((e) => setError(e.message ?? "Could not load vendor cases."))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function handleSubmit() {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res = await onboardVendor({
        vendor_name: name,
        vendor_gstin: gstin || undefined,
        vendor_pan: pan || undefined,
        sector,
        documents: files,
      });
      setResult(res);
      setName(""); setGstin(""); setPan(""); setFiles([]);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <p className="font-body text-gold-600 text-xs tracking-widest uppercase font-semibold mb-1">Vendor Onboarding</p>
        <h1 className="font-display text-2xl sm:text-3xl text-brown-900 font-bold mb-1">KYC/KYB Vendor Checks</h1>
        <p className="font-body text-sm text-brown-600 max-w-xl leading-relaxed">
          Onboard a new vendor. The pipeline checks for missing mandatory documents, PEP/sanctions
          matches, and UBO issues. Any PEP hit unconditionally escalates to human review.
        </p>
      </div>

      {/* Onboarding form */}
      <div className="rounded-2xl border border-stone-200 bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-stone-100">
          <h2 className="font-body text-sm font-semibold text-brown-900">New Vendor</h2>
          <p className="font-body text-xs text-brown-400 mt-0.5">Fill in vendor details and attach KYC documents</p>
        </div>

        <div className="px-5 py-5 space-y-4">
          {/* Vendor name */}
          <div>
            <label className="font-body text-xs font-semibold text-brown-600 block mb-1.5">Vendor Name *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Apex Trading Pvt Ltd"
              className="w-full rounded-xl border border-stone-200 bg-cream-50 px-3.5 py-2.5 font-body text-sm text-brown-900 placeholder:text-brown-300 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400 transition-colors"
            />
          </div>

          {/* GSTIN + PAN */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="font-body text-xs font-semibold text-brown-600 block mb-1.5">GSTIN</label>
              <input
                value={gstin}
                onChange={(e) => setGstin(e.target.value)}
                placeholder="22AAAAA0000A1Z5 (optional)"
                className="w-full rounded-xl border border-stone-200 bg-cream-50 px-3.5 py-2.5 font-body text-sm text-brown-900 placeholder:text-brown-300 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400 transition-colors"
              />
            </div>
            <div>
              <label className="font-body text-xs font-semibold text-brown-600 block mb-1.5">PAN</label>
              <input
                value={pan}
                onChange={(e) => setPan(e.target.value)}
                placeholder="ABCDE1234F (optional)"
                className="w-full rounded-xl border border-stone-200 bg-cream-50 px-3.5 py-2.5 font-body text-sm text-brown-900 placeholder:text-brown-300 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400 transition-colors"
              />
            </div>
          </div>

          {/* Sector */}
          <div>
            <label className="font-body text-xs font-semibold text-brown-600 block mb-1.5">Sector</label>
            <select
              value={sector}
              onChange={(e) => setSector(e.target.value)}
              className="w-full rounded-xl border border-stone-200 bg-cream-50 px-3.5 py-2.5 font-body text-sm text-brown-900 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400 transition-colors"
            >
              {SECTORS.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>

          {/* Document upload */}
          <div>
            <label className="font-body text-xs font-semibold text-brown-600 block mb-1.5">KYC Documents</label>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-2 rounded-xl border border-dashed border-stone-300 bg-stone-50 hover:bg-stone-100 hover:border-stone-400 px-4 py-2.5 transition-colors font-body text-sm text-brown-600"
            >
              <Upload className="w-4 h-4 text-brown-400" />
              {files.length > 0 ? `${files.length} document${files.length > 1 ? "s" : ""} selected` : "Attach onboarding documents"}
            </button>
            <input ref={fileInputRef} type="file" multiple className="hidden" onChange={(e) => setFiles(Array.from(e.target.files || []))} />
          </div>

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={submitting || !name.trim()}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-brown-900 text-cream-50 font-body font-semibold py-3 hover:bg-brown-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Running KYC checks…</> : <>
              <FileCheck className="w-4 h-4" /> Onboard Vendor
            </>}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 rounded-xl bg-red-50 border border-red-200 p-4">
          <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
          <p className="font-body text-sm text-red-700">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600 font-body text-lg leading-none">&times;</button>
        </div>
      )}

      {/* Result card */}
      {result && (
        <div className="rounded-2xl border border-brown-900/10 bg-brown-900 p-5 shadow-lg">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-cream-50/10 flex items-center justify-center">
                <CheckCircle className="w-4 h-4 text-green-400" />
              </div>
              <div>
                <p className="font-body text-sm font-semibold text-cream-50">{result.vendor_name}</p>
                <p className="font-body text-xs text-cream-50/50">{sector}</p>
              </div>
            </div>
            {KYC_BADGE[result.kyc_status] && (
              <span className={`font-body text-xs font-semibold uppercase tracking-wide border rounded-full px-3 py-1 ${KYC_BADGE[result.kyc_status].cls}`}>
                {KYC_BADGE[result.kyc_status].label}
              </span>
            )}
          </div>

          {result.pep_flags?.length > 0 && (
            <div className="flex items-start gap-2 rounded-lg bg-red-900/30 border border-red-700/30 px-3 py-2.5 mb-3">
              <ShieldAlert className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
              <div>
                <p className="font-body text-xs font-semibold text-red-300">PEP / Sanctions Match Detected</p>
                <p className="font-body text-xs text-red-400/80 mt-0.5">{result.pep_flags.join(", ")}</p>
              </div>
            </div>
          )}

          {result.missing_documents?.length > 0 && (
            <div className="flex items-start gap-2 rounded-lg bg-amber-900/20 border border-amber-700/30 px-3 py-2.5 mb-3">
              <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
              <div>
                <p className="font-body text-xs font-semibold text-amber-300">Missing Documents</p>
                <p className="font-body text-xs text-amber-400/80 mt-0.5">{result.missing_documents.join(", ")}</p>
              </div>
            </div>
          )}

          {result.requires_approval && (
            <div className="flex items-center gap-2 rounded-lg bg-gold-500/15 border border-gold-500/20 px-3 py-2">
              <AlertTriangle className="w-3.5 h-3.5 text-gold-400 shrink-0" />
              <p className="font-body text-xs text-gold-300">
                Staged for human approval #{result.approval_id?.slice(0, 8)}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Case list */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-body text-sm font-semibold text-brown-900">
            Vendor Cases {!loading && cases.length > 0 && <span className="text-brown-400 font-normal">({cases.length})</span>}
          </h2>
          <button onClick={load} disabled={loading} className="flex items-center gap-1.5 font-body text-xs text-brown-500 hover:text-brown-800 disabled:opacity-40 transition-colors">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>

        {loading ? (
          <Skeleton rows={3} />
        ) : cases.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-stone-200 p-10 text-center">
            <Building2 className="w-8 h-8 text-stone-300 mx-auto mb-3" />
            <p className="font-body text-sm text-brown-500">No vendor cases yet.</p>
            <p className="font-body text-xs text-brown-400 mt-1">Onboard your first vendor above.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {cases.map((c) => {
              const badge = KYC_BADGE[c.kyc_status] ?? { label: c.kyc_status, cls: "bg-stone-100 text-stone-600 border-stone-200" };
              return (
                <button
                  key={c.case_id}
                  onClick={() => openCase(c)}
                  className="w-full flex items-center justify-between rounded-xl border border-stone-200 bg-white px-4 py-3 hover:border-gold-400/60 hover:shadow-sm transition-all text-left"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-stone-100 flex items-center justify-center shrink-0">
                      <Building2 className="w-4 h-4 text-brown-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="font-body text-sm font-medium text-brown-900 truncate">{c.vendor_name}</p>
                      <p className="font-body text-xs text-brown-400">
                        {c.sector || "—"} &middot; {c.missing_documents?.length ?? 0} missing doc{c.missing_documents?.length !== 1 ? "s" : ""}
                        {c.pep_flags?.length > 0 && <> &middot; {c.pep_flags.length} PEP flag{c.pep_flags.length !== 1 ? "s" : ""}</>}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`font-body text-[11px] font-semibold uppercase tracking-wide border rounded-full px-2.5 py-0.5 ${badge.cls}`}>
                      {badge.label}
                    </span>
                    <ChevronRight className="w-3.5 h-3.5 text-brown-300" />
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Case detail drawer */}
      <DetailDrawer
        isOpen={selectedCase !== null}
        onClose={() => setSelectedCase(null)}
        title={selectedCase?.vendor_name ?? ""}
        subtitle={selectedCase?.sector || undefined}
        riskTier={selectedCase?.risk_tier}
        loading={drawerLoading}
      >
        {selectedCase && (
          <>
            <DrawerSection label="Vendor Details">
              <FactGrid
                items={[
                  { label: "KYC Status", value: KYC_BADGE[selectedCase.kyc_status]?.label ?? selectedCase.kyc_status },
                  { label: "GSTIN", value: selectedCase.vendor_gstin },
                  { label: "Onboarded", value: selectedCase.created_at ? new Date(selectedCase.created_at).toLocaleDateString("en-IN") : undefined },
                  { label: "Requires Approval", value: selectedCase.requires_approval ? "Yes" : "No" },
                ]}
              />
            </DrawerSection>

            <DrawerSection label={`Missing Documents (${selectedCase.missing_documents?.length ?? 0})`}>
              <FlagList
                tone="amber"
                empty="No mandatory documents are missing."
                items={(selectedCase.missing_documents ?? []).map((d: string) => ({ title: d }))}
              />
            </DrawerSection>

            <DrawerSection label={`PEP / Sanctions Matches (${selectedCase.pep_flags?.length ?? 0})`}>
              <FlagList
                tone="red"
                empty="No PEP or sanctions matches found."
                items={(selectedCase.pep_flags ?? []).map((f: string) => ({ title: f, detail: "Unconditionally escalates to human review." }))}
              />
            </DrawerSection>

            <DrawerSection label={`UBO Issues (${selectedCase.ubo_issues?.length ?? 0})`}>
              <FlagList
                tone="amber"
                empty="No beneficial-ownership issues found."
                items={(selectedCase.ubo_issues ?? []).map((u: string) => ({ title: u }))}
              />
            </DrawerSection>

            <DrawerSection label="How This Was Analyzed">
              <AuditTimeline entries={caseAuditEntries} />
            </DrawerSection>
          </>
        )}
      </DetailDrawer>
    </div>
  );
}
