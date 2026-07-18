"use client";

import { useEffect, useRef, useState } from "react";
import { uploadPolicy, listPolicies } from "@/lib/compliance-api";
import { DetailDrawer, DrawerSection, FactGrid, FlagList } from "@/components/compliance/DetailDrawer";
import { Upload, FileText, Loader2, AlertTriangle, RefreshCw, BookOpen, CheckCircle, ChevronRight } from "lucide-react";

function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-14 rounded-xl bg-stone-200/60 animate-pulse" />
      ))}
    </div>
  );
}

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<Record<string, any>[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Detail drawer — full compliance-gap list for one past policy (already in list response)
  const [selectedPolicy, setSelectedPolicy] = useState<Record<string, any> | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    listPolicies()
      .then((res) => setPolicies(res.policies ?? []))
      .catch((e) => setError(e.message ?? "Could not load policies."))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function handleFile(file: File) {
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const res = await uploadPolicy(file);
      setResult(res);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <p className="font-body text-gold-600 text-xs tracking-widest uppercase font-semibold mb-1">Policy Library</p>
        <h1 className="font-display text-2xl sm:text-3xl text-brown-900 font-bold mb-1">Policy Documents & Compliance Gaps</h1>
        <p className="font-body text-sm text-brown-600 max-w-xl leading-relaxed">
          Upload an internal policy document. Gemma compares it against the 40-rule compliance
          catalogue and flags which rules the policy doesn&apos;t adequately cover.
        </p>
      </div>

      {/* Upload zone */}
      <div
        onClick={() => !uploading && fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-10 text-center transition-colors ${
          uploading
            ? "border-gold-400/50 bg-gold-500/5 cursor-default"
            : "border-stone-300 hover:border-gold-400/60 hover:bg-gold-500/4 cursor-pointer"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.txt"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 text-gold-500 animate-spin" />
            <p className="font-body text-sm text-brown-700">Comparing against 40 rules with Gemma…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-stone-100 flex items-center justify-center">
              <Upload className="w-5 h-5 text-brown-400" />
            </div>
            <div>
              <p className="font-body text-sm font-medium text-brown-800">Drop a policy document here, or click to browse</p>
              <p className="font-body text-xs text-brown-400 mt-0.5">Supports PDF, DOCX, TXT</p>
            </div>
          </div>
        )}
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
                <p className="font-body text-sm font-semibold text-cream-50">{result.title}</p>
                <p className="font-body text-xs text-cream-50/50">
                  {result.gap_analysis_method === "gemma" ? "Analysed with Gemma" : "Keyword fallback analysis"}
                </p>
              </div>
            </div>
            {result.compliance_gaps?.length > 0 && (
              <span className="font-body text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-full px-2.5 py-0.5">
                {result.compliance_gaps.length} gap{result.compliance_gaps.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {result.compliance_gaps?.length === 0 ? (
            <div className="flex items-center gap-2 rounded-lg bg-emerald-900/20 border border-emerald-700/30 px-3 py-2.5">
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
              <p className="font-body text-xs text-emerald-300">No significant gaps found against the rule catalogue.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {result.compliance_gaps?.map((g: any, i: number) => (
                <div key={i} className="flex items-start gap-2.5 bg-cream-50/8 rounded-lg px-3 py-2.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" />
                  <div>
                    <p className="font-body text-xs font-semibold text-cream-50">{g.rule_code}</p>
                    <p className="font-body text-xs text-cream-50/60 mt-0.5">{g.gap_description}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Policy list */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-body text-sm font-semibold text-brown-900">
            Policy Library {!loading && policies.length > 0 && <span className="text-brown-400 font-normal">({policies.length})</span>}
          </h2>
          <button onClick={load} disabled={loading} className="flex items-center gap-1.5 font-body text-xs text-brown-500 hover:text-brown-800 disabled:opacity-40 transition-colors">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>

        {loading ? (
          <Skeleton rows={3} />
        ) : policies.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-stone-200 p-10 text-center">
            <BookOpen className="w-8 h-8 text-stone-300 mx-auto mb-3" />
            <p className="font-body text-sm text-brown-500">No policies uploaded yet.</p>
            <p className="font-body text-xs text-brown-400 mt-1">Upload your first policy document above.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {policies.map((p) => (
              <button
                key={p.policy_id}
                onClick={() => setSelectedPolicy(p)}
                className="w-full flex items-center justify-between rounded-xl border border-stone-200 bg-white px-4 py-3 hover:border-gold-400/60 hover:shadow-sm transition-all text-left"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-stone-100 flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-brown-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="font-body text-sm font-medium text-brown-900 truncate">
                      {p.title} <span className="text-brown-400 font-normal">v{p.version}</span>
                    </p>
                    <p className="font-body text-xs text-brown-400">
                      {p.gap_count > 0 ? `${p.gap_count} compliance gap${p.gap_count !== 1 ? "s" : ""} identified` : "No gaps found"}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {p.gap_count > 0 ? (
                    <span className="font-body text-[11px] font-semibold uppercase tracking-wide bg-amber-50 text-amber-700 border border-amber-200 rounded-full px-2.5 py-0.5">
                      Review Needed
                    </span>
                  ) : (
                    <span className="font-body text-[11px] font-semibold uppercase tracking-wide bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full px-2.5 py-0.5">
                      OK
                    </span>
                  )}
                  <ChevronRight className="w-3.5 h-3.5 text-brown-300" />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Policy detail drawer */}
      <DetailDrawer
        isOpen={selectedPolicy !== null}
        onClose={() => setSelectedPolicy(null)}
        title={selectedPolicy?.title ?? ""}
        subtitle={selectedPolicy ? `Version ${selectedPolicy.version}` : undefined}
      >
        {selectedPolicy && (
          <>
            <DrawerSection label="Policy Details">
              <FactGrid
                items={[
                  { label: "Version", value: selectedPolicy.version },
                  { label: "Effective Date", value: selectedPolicy.effective_date },
                  { label: "Uploaded", value: selectedPolicy.created_at ? new Date(selectedPolicy.created_at).toLocaleDateString("en-IN") : undefined },
                  { label: "Compliance Gaps", value: selectedPolicy.gap_count },
                ]}
              />
            </DrawerSection>

            <DrawerSection label={`Compliance Gaps (${selectedPolicy.compliance_gaps?.length ?? 0})`}>
              <FlagList
                tone="amber"
                empty="No significant gaps found against the 40-rule catalogue."
                items={(selectedPolicy.compliance_gaps ?? []).map((g: any) => ({
                  title: g.rule_code,
                  detail: g.gap_description,
                }))}
              />
            </DrawerSection>
          </>
        )}
      </DetailDrawer>
    </div>
  );
}
