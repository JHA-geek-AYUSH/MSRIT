"use client";

import { useEffect, useState } from "react";
import { getAuditTrail } from "@/lib/compliance-api";
import { DetailDrawer, DrawerSection, FactGrid } from "@/components/compliance/DetailDrawer";
import { Search, RefreshCw, ChevronRight, ClipboardList } from "lucide-react";

function Skeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-14 rounded-xl bg-stone-200/60 animate-pulse" />
      ))}
    </div>
  );
}

const ENTITY_TYPES = ["", "invoice", "transaction_batch", "vendor_onboarding_case"];

const ENTITY_LABELS: Record<string, string> = {
  "": "All events",
  invoice: "Invoices",
  transaction_batch: "Transactions",
  vendor_onboarding_case: "Vendor KYC",
};

export default function AuditPage() {
  const [entries, setEntries] = useState<Record<string, any>[]>([]);
  const [loading, setLoading] = useState(true);
  const [entityType, setEntityType] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Record<string, any> | null>(null);

  function load() {
    setLoading(true);
    getAuditTrail({ entity_type: entityType || undefined, limit: 200 })
      .then((res) => setEntries(res.entries ?? []))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }
  useEffect(load, [entityType]);

  const filtered = entries.filter((e) => {
    const q = search.toLowerCase();
    if (!q) return true;
    return (
      String(e.action ?? "").toLowerCase().includes(q) ||
      String(e.actor ?? "").toLowerCase().includes(q) ||
      String(e.entity_id ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <p className="font-body text-gold-600 text-xs tracking-widest uppercase font-semibold mb-1">Full Event History</p>
        <h1 className="font-display text-2xl sm:text-3xl text-brown-900 font-bold mb-1">Audit Log</h1>
        <p className="font-body text-sm text-brown-600 max-w-xl leading-relaxed">
          Every append-only event the platform recorded while processing invoices, transactions, and
          vendor onboarding cases — uploads, extractions, risk scoring, and approval requests.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-brown-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by action, actor, or entity id…"
            className="w-full rounded-xl border border-stone-200 bg-white pl-9 pr-4 py-2.5 font-body text-sm text-brown-900 placeholder:text-brown-300 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400 transition-colors shadow-sm"
          />
        </div>
        <select
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
          className="rounded-xl border border-stone-200 bg-white px-3.5 py-2.5 font-body text-sm text-brown-900 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400 transition-colors shadow-sm"
        >
          {ENTITY_TYPES.map((t) => (
            <option key={t} value={t}>{ENTITY_LABELS[t]}</option>
          ))}
        </select>
        <button onClick={load} disabled={loading} className="flex items-center gap-1.5 font-body text-xs text-brown-500 hover:text-brown-800 disabled:opacity-40 transition-colors">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* Event list */}
      {loading ? (
        <Skeleton />
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-stone-200 p-10 text-center">
          <ClipboardList className="w-8 h-8 text-stone-300 mx-auto mb-3" />
          <p className="font-body text-sm text-brown-500">No audit events recorded yet.</p>
          <p className="font-body text-xs text-brown-400 mt-1">Events appear here as you process invoices, transactions, and vendors.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((e) => (
            <button
              key={e.id}
              onClick={() => setSelected(e)}
              className="w-full flex items-center justify-between rounded-xl border border-stone-200 bg-white px-4 py-3 hover:border-gold-400/60 hover:shadow-sm transition-all text-left"
            >
              <div className="min-w-0">
                <p className="font-body text-sm font-medium text-brown-900 capitalize truncate">
                  {String(e.action ?? "event").replace(/_/g, " ")}
                </p>
                <p className="font-body text-xs text-brown-400">
                  {e.timestamp ? new Date(e.timestamp).toLocaleString("en-IN") : "—"} &middot; {e.actor || "system"}
                  {e.entity_type && <> &middot; {ENTITY_LABELS[e.entity_type] ?? e.entity_type}</>}
                </p>
              </div>
              <ChevronRight className="w-3.5 h-3.5 text-brown-300 shrink-0" />
            </button>
          ))}
        </div>
      )}

      {/* Event detail drawer */}
      <DetailDrawer
        isOpen={selected !== null}
        onClose={() => setSelected(null)}
        title={String(selected?.action ?? "").replace(/_/g, " ")}
        subtitle={selected?.timestamp ? new Date(selected.timestamp).toLocaleString("en-IN") : undefined}
      >
        {selected && (
          <>
            <DrawerSection label="Event">
              <FactGrid
                items={[
                  { label: "Actor", value: selected.actor },
                  { label: "Entity Type", value: selected.entity_type },
                  { label: "Entity ID", value: selected.entity_id?.slice?.(0, 8) },
                  { label: "Workflow ID", value: selected.workflow_id?.slice?.(0, 8) },
                ]}
              />
            </DrawerSection>
            {selected.metadata && Object.keys(selected.metadata).length > 0 && (
              <DrawerSection label="Details">
                <pre className="font-body text-[11px] text-brown-700 bg-white border border-stone-200 rounded-xl px-3 py-2.5 overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(selected.metadata, null, 2)}
                </pre>
              </DrawerSection>
            )}
          </>
        )}
      </DetailDrawer>
    </div>
  );
}
