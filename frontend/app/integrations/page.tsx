"use client";

import { useEffect, useState } from "react";
import { Header } from "@/components/layout/Header";
import { getConnectorStatus, getComposioToolkits, connectComposioToolkit } from "@/lib/compliance-api";

const TOOLKIT_LABELS: Record<string, string> = {
  OUTLOOK: "Outlook",
  ONEDRIVE: "OneDrive / SharePoint",
  GOOGLESHEETS: "Google Sheets (Excel-equivalent)",
  SLACK: "Slack",
};

function StatusPill({ configured, connected }: { configured: boolean; connected?: boolean }) {
  if (!configured) return <span className="text-[10px] font-body uppercase border border-brown-500/25 text-brown-500 rounded-full px-2.5 py-1">Not configured</span>;
  if (connected) return <span className="text-[10px] font-body uppercase border border-olive-400/40 bg-olive-400/15 text-olive-400 rounded-full px-2.5 py-1">Connected</span>;
  return <span className="text-[10px] font-body uppercase border border-error-500/40 bg-error-500/10 text-error-500 rounded-full px-2.5 py-1">Configured, not reachable</span>;
}

export default function IntegrationsPage() {
  const [status, setStatus] = useState<Record<string, any>>({});
  const [toolkits, setToolkits] = useState<{ configured: boolean; toolkits: string[] }>({ configured: false, toolkits: [] });
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getConnectorStatus(), getComposioToolkits()])
      .then(([s, t]) => {
        setStatus(s);
        setToolkits(t);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleConnect(toolkit: string) {
    setError(null);
    setConnecting(toolkit);
    try {
      const res = await connectComposioToolkit(toolkit);
      if (res.redirect_url) {
        window.open(res.redirect_url, "_blank", "noopener,noreferrer,width=520,height=680");
      } else {
        setError("Composio didn't return an authorization URL — check COMPOSIO_API_KEY and the toolkit slug on the backend.");
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setConnecting(null);
    }
  }

  return (
    <div className="min-h-screen bg-cream-50">
      <Header />
      <main className="max-w-4xl mx-auto px-6 py-12">
        <p className="font-body text-gold-500 text-sm tracking-widest uppercase mb-2">Integrations</p>
        <h1 className="font-display text-4xl text-brown-900 mb-3">Connect SAP, Outlook, Excel & SharePoint</h1>
        <p className="font-body text-brown-700 mb-8 max-w-2xl">
          Outlook, OneDrive/SharePoint, Google Sheets, and Slack connect through Composio's
          managed OAuth. SAP and a second local finance database connect directly — those
          are configured server-side via <code className="text-xs bg-brown-900/5 px-1 py-0.5 rounded">KEYS.md</code>.
        </p>

        {error && <div className="bg-error-500/10 border border-error-500/30 rounded-lg p-4 mb-6 font-body text-sm text-error-500">{error}</div>}

        {loading ? (
          <p className="font-body text-brown-500">Checking connector status…</p>
        ) : (
          <div className="space-y-6">
            {/* Composio-managed toolkits */}
            <div>
              <p className="font-display text-lg text-brown-900 mb-3">Composio-managed apps</p>
              {!toolkits.configured && (
                <div className="bg-gold-500/10 border border-gold-500/30 rounded-lg p-4 mb-3 font-body text-sm text-brown-700">
                  Composio isn't configured yet — set <code className="text-xs bg-brown-900/5 px-1 py-0.5 rounded">COMPOSIO_API_KEY</code> on the backend (see KEYS.md §3).
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {toolkits.toolkits.map((tk) => (
                  <div key={tk} className="bg-stone-200/40 border border-brown-500/15 rounded-xl p-5 flex items-center justify-between">
                    <div>
                      <p className="font-body font-medium text-brown-900">{TOOLKIT_LABELS[tk] || tk}</p>
                      <p className="font-body text-xs text-brown-500 mt-0.5">via Composio</p>
                    </div>
                    <button
                      onClick={() => handleConnect(tk)}
                      disabled={!toolkits.configured || connecting === tk}
                      className="text-xs font-body bg-brown-900 text-cream-50 rounded-lg px-4 py-2 hover:bg-brown-700 transition-colors disabled:opacity-40"
                    >
                      {connecting === tk ? "Opening…" : "Connect"}
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* Direct connectors */}
            <div>
              <p className="font-display text-lg text-brown-900 mb-3">Direct connectors</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {Object.entries(status)
                  .filter(([name]) => name !== "composio")
                  .map(([name, s]: [string, any]) => (
                    <div key={name} className="bg-stone-200/40 border border-brown-500/15 rounded-xl p-5">
                      <div className="flex items-center justify-between">
                        <p className="font-body font-medium text-brown-900 capitalize">{name.replace(/_/g, " ")}</p>
                        <StatusPill configured={s.configured} connected={s.connected} />
                      </div>
                      {s.reason && <p className="font-body text-xs text-brown-500 mt-1.5">{s.reason}</p>}
                    </div>
                  ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
