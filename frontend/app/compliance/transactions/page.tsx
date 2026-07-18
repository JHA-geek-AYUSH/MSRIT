"use client";

import { useEffect, useState } from "react";
import { SeverityBadge } from "@/components/compliance/SeverityBadge";
import { ingestTransactions, listTransactionBatches, getAuditTrail, type TransactionRecord } from "@/lib/compliance-api";
import { DetailDrawer, DrawerSection, FactGrid, FlagList, AuditTimeline } from "@/components/compliance/DetailDrawer";
import { Plus, Trash2, Loader2, AlertTriangle, RefreshCw, ArrowLeftRight, CheckCircle, ChevronRight } from "lucide-react";

function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-14 rounded-xl bg-stone-200/60 animate-pulse" />
      ))}
    </div>
  );
}

const BLANK_ROW: TransactionRecord = {
  external_id: "",
  supplier: "",
  amount: 0,
  transaction_date: new Date().toISOString().slice(0, 10),
  invoice_number: "",
  description: "",
};

export default function TransactionsPage() {
  const [rows, setRows] = useState<TransactionRecord[]>([{ ...BLANK_ROW }]);
  const [batches, setBatches] = useState<Record<string, any>[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // Detail drawer — duplicate/mismatch/unusual findings + reasoning for one past batch
  const [selectedBatch, setSelectedBatch] = useState<Record<string, any> | null>(null);
  const [batchAuditEntries, setBatchAuditEntries] = useState<Record<string, any>[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);

  function openBatch(b: Record<string, any>) {
    setSelectedBatch(b);
    setDrawerLoading(true);
    getAuditTrail({ entity_type: "transaction_batch", entity_id: b.batch_id })
      .then((res) => setBatchAuditEntries(res.entries ?? []))
      .catch(() => setBatchAuditEntries([]))
      .finally(() => setDrawerLoading(false));
  }

  function load() {
    setLoading(true);
    setError(null);
    listTransactionBatches()
      .then((res) => setBatches(res.batches ?? []))
      .catch((e) => setError(e.message ?? "Could not load batches."))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  function updateRow(i: number, field: keyof TransactionRecord, value: string | number) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [field]: value } : r)));
  }
  function addRow() {
    setRows((prev) => [...prev, { ...BLANK_ROW, external_id: `txn-${prev.length + 1}` }]);
  }
  function removeRow(i: number) {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const payload = rows.map((r, i) => ({ ...r, external_id: r.external_id || `txn-${i + 1}` }));
      const res = await ingestTransactions(payload, "manual");
      setResult(res);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  const FIELD_LABELS = ["Supplier *", "Amount (₹) *", "Date *", "Invoice #", "Description"];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <p className="font-body text-gold-600 text-xs tracking-widest uppercase font-semibold mb-1">Transaction Monitoring</p>
        <h1 className="font-display text-2xl sm:text-3xl text-brown-900 font-bold mb-1">AML/CFT Batch Ingestion</h1>
        <p className="font-body text-sm text-brown-600 max-w-xl leading-relaxed">
          Enter a batch of transactions to scan for duplicate payments, invoice mismatches, and unusual
          patterns. Critical findings trigger human approval.
        </p>
      </div>

      {/* Transaction entry form */}
      <div className="rounded-2xl border border-stone-200 bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-stone-100">
          <h2 className="font-body text-sm font-semibold text-brown-900">Enter Transactions</h2>
          <p className="font-body text-xs text-brown-400 mt-0.5">Add one or more rows then click Ingest &amp; Scan</p>
        </div>

        {/* Column headers */}
        <div className="hidden sm:grid sm:grid-cols-[2fr_1fr_1fr_1fr_2fr_32px] gap-2 px-5 pt-3 pb-1">
          {FIELD_LABELS.map((l) => (
            <p key={l} className="font-body text-[10px] font-semibold uppercase tracking-wider text-brown-300">{l}</p>
          ))}
          <span />
        </div>

        <div className="px-5 pb-4 space-y-2 mt-1">
          {rows.map((row, i) => (
            <div key={i} className="grid grid-cols-2 sm:grid-cols-[2fr_1fr_1fr_1fr_2fr_32px] gap-2 items-center">
              <input
                value={row.supplier}
                onChange={(e) => updateRow(i, "supplier", e.target.value)}
                placeholder="Supplier name"
                className="rounded-lg border border-stone-200 bg-cream-50 px-3 py-2 font-body text-sm text-brown-900 placeholder:text-brown-300 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400"
              />
              <input
                type="number"
                value={row.amount || ""}
                onChange={(e) => updateRow(i, "amount", Number(e.target.value))}
                placeholder="0.00"
                className="rounded-lg border border-stone-200 bg-cream-50 px-3 py-2 font-body text-sm text-brown-900 placeholder:text-brown-300 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400"
              />
              <input
                type="date"
                value={row.transaction_date}
                onChange={(e) => updateRow(i, "transaction_date", e.target.value)}
                className="rounded-lg border border-stone-200 bg-cream-50 px-3 py-2 font-body text-sm text-brown-900 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400"
              />
              <input
                value={row.invoice_number || ""}
                onChange={(e) => updateRow(i, "invoice_number", e.target.value)}
                placeholder="INV-001"
                className="rounded-lg border border-stone-200 bg-cream-50 px-3 py-2 font-body text-sm text-brown-900 placeholder:text-brown-300 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400"
              />
              <input
                value={row.description || ""}
                onChange={(e) => updateRow(i, "description", e.target.value)}
                placeholder="Optional description"
                className="rounded-lg border border-stone-200 bg-cream-50 px-3 py-2 font-body text-sm text-brown-900 placeholder:text-brown-300 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400"
              />
              <button
                onClick={() => removeRow(i)}
                disabled={rows.length === 1}
                className="flex items-center justify-center w-8 h-8 rounded-lg text-brown-300 hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-20 disabled:cursor-not-allowed"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>

        <div className="px-5 pb-5 flex flex-col sm:flex-row gap-2">
          <button
            onClick={addRow}
            className="flex items-center justify-center gap-1.5 font-body text-sm text-brown-600 border border-stone-200 rounded-xl px-4 py-2.5 hover:bg-stone-50 hover:border-stone-300 transition-colors"
          >
            <Plus className="w-4 h-4" /> Add row
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || rows.every((r) => !r.supplier)}
            className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-brown-900 text-cream-50 font-body font-semibold py-2.5 hover:bg-brown-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Scanning…</> : "Ingest & Scan Batch"}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 rounded-xl bg-red-50 border border-red-200 p-4">
          <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
          <p className="font-body text-sm text-red-700">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600">×</button>
        </div>
      )}

      {/* Result card */}
      {result && (
        <div className="rounded-2xl border border-brown-900/10 bg-brown-900 p-5 shadow-lg">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-cream-50/10 flex items-center justify-center">
                <CheckCircle className="w-4 h-4 text-green-400" />
              </div>
              <div>
                <p className="font-body text-sm font-semibold text-cream-50">Batch {result.batch_id?.slice(0, 8)}</p>
                <p className="font-body text-xs text-cream-50/50">{result.total_processed} transactions processed</p>
              </div>
            </div>
            <SeverityBadge severity={result.risk_assessment?.risk_tier} size="md" />
          </div>

          {result.risk_assessment?.reasoning && (
            <p className="font-body text-xs text-cream-50/70 mb-4 leading-relaxed">{result.risk_assessment.reasoning}</p>
          )}

          <div className="grid grid-cols-3 gap-3 mb-4">
            {[
              { label: "Duplicates", value: result.duplicate_payments?.length ?? 0, warn: result.duplicate_payments?.length > 0 },
              { label: "Mismatches", value: result.invoice_mismatches?.length ?? 0, warn: result.invoice_mismatches?.length > 0 },
              { label: "Unusual", value: result.unusual_transactions?.length ?? 0, warn: result.unusual_transactions?.length > 0 },
            ].map((stat) => (
              <div key={stat.label} className="rounded-xl bg-cream-50/8 px-3 py-2.5 text-center">
                <p className={`font-body text-lg font-bold ${stat.warn ? "text-gold-400" : "text-cream-50"}`}>{stat.value}</p>
                <p className="font-body text-[10px] text-cream-50/50 uppercase tracking-wide">{stat.label}</p>
              </div>
            ))}
          </div>

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

      {/* Batch history */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-body text-sm font-semibold text-brown-900">
            Recent Batches {!loading && batches.length > 0 && <span className="text-brown-400 font-normal">({batches.length})</span>}
          </h2>
          <button onClick={load} disabled={loading} className="flex items-center gap-1.5 font-body text-xs text-brown-500 hover:text-brown-800 transition-colors disabled:opacity-40">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>

        {loading ? (
          <Skeleton rows={3} />
        ) : batches.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-stone-200 p-10 text-center">
            <ArrowLeftRight className="w-8 h-8 text-stone-300 mx-auto mb-3" />
            <p className="font-body text-sm text-brown-500">No batches ingested yet.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {batches.map((b) => (
              <button
                key={b.batch_id}
                onClick={() => openBatch(b)}
                className="w-full flex items-center justify-between rounded-xl border border-stone-200 bg-white px-4 py-3 hover:border-gold-400/60 hover:shadow-sm transition-all text-left"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-stone-100 flex items-center justify-center shrink-0">
                    <ArrowLeftRight className="w-4 h-4 text-brown-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="font-body text-sm font-medium text-brown-900 capitalize">{b.source} &middot; {b.total_processed} transactions &middot; {b.flagged_count} flagged</p>
                    <p className="font-body text-xs text-brown-400">{b.created_at ? new Date(b.created_at).toLocaleString("en-IN") : "—"}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <SeverityBadge severity={b.risk_tier} />
                  <ChevronRight className="w-3.5 h-3.5 text-brown-300" />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Batch detail drawer */}
      <DetailDrawer
        isOpen={selectedBatch !== null}
        onClose={() => setSelectedBatch(null)}
        title={`Batch · ${selectedBatch?.source ?? ""}`}
        subtitle={selectedBatch?.created_at ? new Date(selectedBatch.created_at).toLocaleString("en-IN") : undefined}
        riskTier={selectedBatch?.risk_tier}
        loading={drawerLoading}
      >
        {selectedBatch && (() => {
          const scoredEntry = batchAuditEntries.find((e) => e.action === "batch_risk_scored");
          const meta = scoredEntry?.metadata ?? {};
          const dup: Record<string, any>[] = meta.duplicate_payments ?? [];
          const mismatch: Record<string, any>[] = meta.invoice_mismatches ?? [];
          const unusual: Record<string, any>[] = meta.unusual_transactions ?? [];
          return (
            <>
              <DrawerSection label="Batch Summary">
                <FactGrid
                  items={[
                    { label: "Source", value: selectedBatch.source },
                    { label: "Processed", value: selectedBatch.total_processed },
                    { label: "Flagged", value: selectedBatch.flagged_count },
                    { label: "Requires Approval", value: selectedBatch.requires_approval ? "Yes" : "No" },
                  ]}
                />
              </DrawerSection>

              {meta.agent_reasoning && (
                <DrawerSection label="AML/CFT Reasoning">
                  <p className="font-body text-xs text-brown-600 leading-relaxed bg-white border border-stone-200 rounded-xl px-3 py-2.5">{meta.agent_reasoning}</p>
                </DrawerSection>
              )}

              <DrawerSection label={`Duplicate Payments (${dup.length})`}>
                <FlagList tone="amber" empty="No duplicate payments detected." items={dup.map((f) => ({ title: f.finding || f.type || "Duplicate payment", detail: f.description || f.detail }))} />
              </DrawerSection>

              <DrawerSection label={`Invoice Mismatches (${mismatch.length})`}>
                <FlagList tone="amber" empty="No PO/invoice mismatches detected." items={mismatch.map((f) => ({ title: f.finding || f.type || "Mismatch", detail: f.description || f.detail }))} />
              </DrawerSection>

              <DrawerSection label={`Unusual Patterns (${unusual.length})`}>
                <FlagList tone="red" empty="No unusual transaction patterns detected." items={unusual.map((f) => ({ title: f.finding || f.type || "Unusual pattern", detail: f.description || f.detail }))} />
              </DrawerSection>

              <DrawerSection label="How This Was Analyzed">
                <AuditTimeline entries={batchAuditEntries} />
              </DrawerSection>
            </>
          );
        })()}
      </DetailDrawer>
    </div>
  );
}
