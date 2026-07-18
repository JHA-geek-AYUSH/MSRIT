"use client";

import { useEffect } from "react";
import { X, Loader2 } from "lucide-react";
import { SeverityBadge } from "./SeverityBadge";

/**
 * Generic slide-over drawer used to show "what the platform actually found /
 * did" for a single row across every FinOps + Compliance list page (vendors,
 * invoices, transactions, policies, triage history, audit log). Rows on those
 * pages open this with `open(item)`; the calling page decides what to render
 * as children based on the item shape.
 */
export function DetailDrawer({
  isOpen,
  onClose,
  title,
  subtitle,
  riskTier,
  loading,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  riskTier?: string | null;
  loading?: boolean;
  children: React.ReactNode;
}) {
  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-brown-900/40 backdrop-blur-[2px] animate-in fade-in duration-150"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative w-full sm:w-[480px] h-full bg-cream-50 shadow-2xl flex flex-col animate-in slide-in-from-right duration-200 overflow-hidden">
        {/* Header */}
        <div className="shrink-0 border-b border-stone-200 bg-white px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-body text-[10px] font-semibold uppercase tracking-widest text-gold-600 mb-1">
                Analysis Detail
              </p>
              <h2 className="font-display text-lg font-bold text-brown-900 truncate">{title}</h2>
              {subtitle && <p className="font-body text-xs text-brown-500 mt-0.5">{subtitle}</p>}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {riskTier !== undefined && riskTier !== null && <SeverityBadge severity={riskTier} size="md" />}
              <button
                onClick={onClose}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-brown-400 hover:text-brown-900 hover:bg-stone-100 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-5 h-5 text-gold-500 animate-spin" />
            </div>
          ) : (
            children
          )}
        </div>
      </div>
    </div>
  );
}

/** Section wrapper with a small uppercase label — used to group fields inside the drawer. */
export function DrawerSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="font-body text-[10px] font-semibold uppercase tracking-widest text-brown-400 mb-2">{label}</p>
      {children}
    </div>
  );
}

/** Simple 2-column key/value fact grid. */
export function FactGrid({ items }: { items: { label: string; value: React.ReactNode }[] }) {
  const shown = items.filter((i) => i.value !== undefined && i.value !== null && i.value !== "");
  if (shown.length === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-3">
      {shown.map((item, i) => (
        <div key={i} className="rounded-xl bg-white border border-stone-200 px-3 py-2.5">
          <p className="font-body text-[10px] text-brown-400 uppercase tracking-wide mb-0.5">{item.label}</p>
          <p className="font-body text-sm text-brown-900 font-medium truncate">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

/** A list of flag/finding style rows with a colored left rail — for missing docs, PEP flags, findings, gaps, etc. */
export function FlagList({
  items,
  tone = "amber",
  empty,
}: {
  items: { title: string; detail?: string }[];
  tone?: "amber" | "red" | "emerald" | "stone";
  empty?: string;
}) {
  const toneMap: Record<string, string> = {
    amber: "bg-amber-50 border-amber-200 text-amber-800",
    red: "bg-red-50 border-red-200 text-red-800",
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-800",
    stone: "bg-stone-50 border-stone-200 text-brown-700",
  };
  if (items.length === 0) {
    return empty ? <p className="font-body text-xs text-brown-400 italic">{empty}</p> : null;
  }
  return (
    <div className="space-y-1.5">
      {items.map((item, i) => (
        <div key={i} className={`rounded-lg border px-3 py-2 ${toneMap[tone]}`}>
          <p className="font-body text-xs font-semibold">{item.title}</p>
          {item.detail && <p className="font-body text-xs opacity-80 mt-0.5">{item.detail}</p>}
        </div>
      ))}
    </div>
  );
}

/** Chronological audit-trail timeline — used to show "how the platform helped analyze" this item. */
export function AuditTimeline({ entries }: { entries: Record<string, any>[] }) {
  if (entries.length === 0) {
    return <p className="font-body text-xs text-brown-400 italic">No audit trail events recorded for this item yet.</p>;
  }
  return (
    <div className="space-y-0">
      {entries.map((e, i) => (
        <div key={e.id ?? i} className="flex gap-3 pb-4 last:pb-0">
          <div className="flex flex-col items-center shrink-0">
            <div className="w-2 h-2 rounded-full bg-gold-500 mt-1.5" />
            {i < entries.length - 1 && <div className="w-px flex-1 bg-stone-200 mt-1" />}
          </div>
          <div className="min-w-0 pb-1">
            <p className="font-body text-xs font-semibold text-brown-900 capitalize">
              {String(e.action ?? "event").replace(/_/g, " ")}
            </p>
            <p className="font-body text-[11px] text-brown-400 mt-0.5">
              {e.timestamp ? new Date(e.timestamp).toLocaleString("en-IN") : "—"} &middot; {e.actor || "system"}
            </p>
            {e.metadata && Object.keys(e.metadata).length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {Object.entries(e.metadata)
                  .filter(([k, v]) => v !== null && v !== undefined && v !== "" && !Array.isArray(v) && typeof v !== "object")
                  .slice(0, 4)
                  .map(([k, v]) => (
                    <span key={k} className="font-body text-[10px] bg-stone-100 text-brown-500 rounded-full px-2 py-0.5">
                      {k.replace(/_/g, " ")}: {String(v)}
                    </span>
                  ))}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
