"use client";

import { useEffect, useRef, useState } from "react";
import { SeverityBadge } from "@/components/compliance/SeverityBadge";
import { uploadInvoice, listInvoices, getAuditTrail, type InvoiceUploadResponse } from "@/lib/compliance-api";
import { DetailDrawer, DrawerSection, FactGrid, FlagList, AuditTimeline } from "@/components/compliance/DetailDrawer";
import { Upload, FileText, Loader2, AlertTriangle, CheckCircle, Clock, RefreshCw, ChevronRight } from "lucide-react";

function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-14 rounded-xl bg-stone-200/60 animate-pulse" />
      ))}
    </div>
  );
}

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Record<string, any>[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [lastResult, setLastResult] = useState<InvoiceUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Detail drawer — extracted fields + findings + audit trail for one past invoice
  const [selectedInvoice, setSelectedInvoice] = useState<Record<string, any> | null>(null);
  const [invoiceAuditEntries, setInvoiceAuditEntries] = useState<Record<string, any>[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);

  function openInvoice(inv: Record<string, any>) {
    setSelectedInvoice(inv);
    setDrawerLoading(true);
    getAuditTrail({ entity_type: "invoice", entity_id: inv.invoice_id })
      .then((res) => setInvoiceAuditEntries(res.entries ?? []))
      .catch(() => setInvoiceAuditEntries([]))
      .finally(() => setDrawerLoading(false));
  }

  function load() {
    setLoading(true);
    setError(null);
    listInvoices()
      .then((res) => setInvoices(res.invoices ?? []))
      .catch((e) => setError(e.message ?? "Could not load invoices."))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function handleFile(file: File) {
    setUploading(true);
    setError(null);
    setLastResult(null);
    try {
      const result = await uploadInvoice(file);
      setLastResult(result);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <p className="font-body text-gold-600 text-xs tracking-widest uppercase font-semibold mb-1">Invoice Workflow</p>
        <h1 className="font-display text-2xl sm:text-3xl text-brown-900 font-bold mb-1">Invoice Processing</h1>
        <p className="font-body text-sm text-brown-600 max-w-xl leading-relaxed">
          Upload a PDF or image invoice. Gemma extracts vendor, amount, GST, and PO fields, then scans for
          duplicate payments and PO mismatches. Critical findings are staged for human approval.
        </p>
      </div>

      {/* Upload zone */}
      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
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
          accept=".pdf,.png,.jpg,.jpeg"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 text-gold-500 animate-spin" />
            <p className="font-body text-sm text-brown-700">Extracting with Gemma, scanning for duplicates…</p>
            <p className="font-body text-xs text-brown-400">This may take a few seconds</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-stone-100 flex items-center justify-center">
              <Upload className="w-5 h-5 text-brown-400" />
            </div>
            <div>
              <p className="font-body text-sm font-medium text-brown-800">Drop an invoice here, or click to browse</p>
              <p className="font-body text-xs text-brown-400 mt-0.5">Supports PDF, PNG, JPG, JPEG</p>
            </div>
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-3 rounded-xl bg-red-50 border border-red-200 p-4">
          <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
          <p className="font-body text-sm text-red-700">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Last upload result */}
      {lastResult && (
        <div className="rounded-2xl border border-brown-900/10 bg-brown-900 p-5 shadow-lg">
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-cream-50/10 flex items-center justify-center">
                <CheckCircle className="w-4 h-4 text-green-400" />
              </div>
              <div>
                <p className="font-body text-sm font-semibold text-cream-50">
                  {lastResult.extracted_fields?.vendor_name || "Invoice"}{" "}
                  — ₹{(lastResult.extracted_fields?.amount_total || 0).toLocaleString("en-IN")}
                </p>
                <p className="font-body text-xs text-cream-50/50">
                  Extraction confidence: {Math.round((lastResult.extracted_fields?.extraction_confidence || 0) * 100)}%
                  {(lastResult.extracted_fields?.extraction_confidence || 0) === 0 && " · regex fallback"}
                </p>
              </div>
            </div>
            <SeverityBadge severity={lastResult.risk_tier} size="md" />
          </div>

          {lastResult.validation_findings.length > 0 && (
            <div className="space-y-1.5 mb-3">
              {lastResult.validation_findings.map((f, i) => (
                <div key={i} className="flex items-start gap-2 bg-cream-50/8 rounded-lg px-3 py-2">
                  <AlertTriangle className="w-3.5 h-3.5 text-gold-400 mt-0.5 shrink-0" />
                  <p className="font-body text-xs text-cream-50/80">{f.finding || JSON.stringify(f)}</p>
                </div>
              ))}
            </div>
          )}

          {lastResult.requires_approval && (
            <div className="flex items-center gap-2 rounded-lg bg-gold-500/15 border border-gold-500/20 px-3 py-2">
              <AlertTriangle className="w-3.5 h-3.5 text-gold-400 shrink-0" />
              <p className="font-body text-xs text-gold-300">
                Critical finding — staged for approval #{lastResult.approval_id?.slice(0, 8)}
              </p>
            </div>
          )}

          {lastResult.audit_trail.length > 0 && (
            <div className="flex items-center gap-3 mt-3 pt-3 border-t border-cream-50/10">
              {lastResult.audit_trail.map((a, i) => (
                <span key={i} className="flex items-center gap-1 font-body text-[10px] text-cream-50/30 uppercase tracking-wider">
                  <CheckCircle className="w-2.5 h-2.5" /> {a.action}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Invoice list */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-body text-sm font-semibold text-brown-900">
            Recent Invoices {!loading && invoices.length > 0 && <span className="text-brown-400 font-normal">({invoices.length})</span>}
          </h2>
          <button onClick={load} disabled={loading} className="flex items-center gap-1.5 font-body text-xs text-brown-500 hover:text-brown-800 transition-colors disabled:opacity-40">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>

        {loading ? (
          <Skeleton rows={4} />
        ) : invoices.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-stone-200 p-10 text-center">
            <FileText className="w-8 h-8 text-stone-300 mx-auto mb-3" />
            <p className="font-body text-sm text-brown-500">No invoices processed yet.</p>
            <p className="font-body text-xs text-brown-400 mt-1">Upload your first invoice above.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {invoices.map((inv) => (
              <button
                key={inv.invoice_id}
                onClick={() => openInvoice(inv)}
                className="w-full flex items-center justify-between rounded-xl border border-stone-200 bg-white px-4 py-3 hover:border-gold-400/60 hover:shadow-sm transition-all text-left"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-stone-100 flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-brown-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="font-body text-sm font-medium text-brown-900 truncate">
                      {inv.vendor_name || "Unknown vendor"} &mdash; {inv.invoice_number || "—"}
                    </p>
                    <p className="font-body text-xs text-brown-400">
                      ₹{Number(inv.amount_total || 0).toLocaleString("en-IN")} &middot;{" "}
                      <span className="capitalize">{inv.status?.replace(/_/g, " ")}</span>
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <SeverityBadge severity={inv.risk_tier} />
                  <ChevronRight className="w-3.5 h-3.5 text-brown-300" />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Invoice detail drawer */}
      <DetailDrawer
        isOpen={selectedInvoice !== null}
        onClose={() => setSelectedInvoice(null)}
        title={selectedInvoice?.vendor_name || "Unknown vendor"}
        subtitle={selectedInvoice?.invoice_number ? `Invoice ${selectedInvoice.invoice_number}` : undefined}
        riskTier={selectedInvoice?.risk_tier}
        loading={drawerLoading}
      >
        {selectedInvoice && (() => {
          const riskEntry = invoiceAuditEntries.find((e) => e.action === "risk_scored");
          const findings: Record<string, any>[] = riskEntry?.metadata?.findings ?? [];
          const extractEntry = invoiceAuditEntries.find((e) => e.action === "extraction_complete");
          return (
            <>
              <DrawerSection label="Extracted Fields">
                <FactGrid
                  items={[
                    { label: "GSTIN", value: selectedInvoice.vendor_gstin },
                    { label: "Invoice Date", value: selectedInvoice.invoice_date },
                    { label: "PO Number", value: selectedInvoice.po_number },
                    { label: "Net Amount", value: selectedInvoice.amount_net != null ? `₹${Number(selectedInvoice.amount_net).toLocaleString("en-IN")}` : undefined },
                    { label: "GST", value: selectedInvoice.amount_gst != null ? `₹${Number(selectedInvoice.amount_gst).toLocaleString("en-IN")}` : undefined },
                    { label: "Total", value: `₹${Number(selectedInvoice.amount_total || 0).toLocaleString("en-IN")}` },
                    { label: "Extraction Method", value: extractEntry?.metadata?.method === "gemma" ? "Gemma" : extractEntry?.metadata?.method ? "Regex fallback" : undefined },
                    { label: "Extraction Confidence", value: `${Math.round((selectedInvoice.extraction_confidence || 0) * 100)}%` },
                  ]}
                />
              </DrawerSection>

              <DrawerSection label={`Duplicate / Mismatch Findings (${findings.length})`}>
                <FlagList
                  tone="amber"
                  empty="No duplicate payments or PO mismatches detected."
                  items={findings.map((f) => ({
                    title: (f.finding || f.type || f.match_kind || "Finding") + (f.severity ? ` · ${String(f.severity).toUpperCase()}` : ""),
                    detail: f.description || f.detail,
                  }))}
                />
              </DrawerSection>

              {selectedInvoice.requires_approval && (
                <DrawerSection label="Approval">
                  <FlagList tone="red" items={[{ title: `Staged for human approval #${selectedInvoice.approval_id?.slice(0, 8) ?? ""}` }]} />
                </DrawerSection>
              )}

              <DrawerSection label="How This Was Analyzed">
                <AuditTimeline entries={invoiceAuditEntries} />
              </DrawerSection>
            </>
          );
        })()}
      </DetailDrawer>
    </div>
  );
}
