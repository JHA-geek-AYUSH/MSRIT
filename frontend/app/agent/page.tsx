"use client";

/**
 * FinTriage AI — Agent Console
 * Real 3-stage assessment pipeline (Stage 0 anomaly -> Stage 1 XGBoost -> Stage 2/3
 * compliance gap scorer) + 7-tool conversational agent (Plan.md Sections 6-7).
 *
 * Replaces the previous stub page, which called a fake in-memory /api/tasks route
 * copy-pasted from the AgentOS project and never talked to the real FastAPI backend.
 *
 * Theme matched to the landing page: cream/brown/gold palette, Playfair (display)
 * + Merriweather (body) fonts, warm editorial look rather than a generic SaaS blue.
 */

import { useState, useRef, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { Header } from "@/components/layout/Header";
import {
  runAssessment,
  runAgent,
  type AssessResponse,
  type AgentResponse,
} from "@/lib/compliance-api";

type ChatMessage = { role: "user" | "agent"; content: string; toolUsed?: string; confidence?: number };

const TIER_STYLES: Record<string, string> = {
  low: "bg-olive-400/15 text-olive-400 border-olive-400/40",
  medium: "bg-gold-500/15 text-gold-500 border-gold-500/40",
  high: "bg-error-500/10 text-error-500 border-error-500/40",
  critical: "bg-error-500 text-cream-50 border-error-500",
};

const EXAMPLE_PROMPTS = [
  "This SME processes ₹8L/month, 42% in cash, with two cross-border transfers to Singapore last quarter and no PEP screening on file.",
  "Retail trading business, ₹2L monthly volume, all domestic, clean onboarding docs, 6 years operating history.",
];

export default function AgentConsolePage() {
  const [description, setDescription] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [sector, setSector] = useState("Trading");
  const [assessing, setAssessing] = useState(false);
  const [assessment, setAssessment] = useState<AssessResponse | null>(null);
  const [assessError, setAssessError] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleAssess() {
    if (!description.trim()) return;
    setAssessing(true);
    setAssessError(null);
    try {
      const result = await runAssessment({
        description,
        business_name: businessName || undefined,
        sector,
        persist: true,
      });
      setAssessment(result);
      setMessages([
        {
          role: "agent",
          content: `Assessment complete: **${result.risk_tier.toUpperCase()}** risk (${Math.round(result.confidence * 100)}% confidence). ${result.findings.length} rule(s) flagged, ₹${Math.round(result.total_penalty_exposure_inr).toLocaleString("en-IN")} estimated exposure. Ask me to explain the risk, simulate a penalty, run a what-if, or generate a report.`,
        },
      ]);
    } catch (e: any) {
      setAssessError(e.message ?? "Assessment failed");
    } finally {
      setAssessing(false);
    }
  }

  async function handleSend() {
    const msg = chatInput.trim();
    if (!msg || chatBusy) return;
    setChatInput("");
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setChatBusy(true);
    try {
      const sessionContext = assessment
        ? {
            last_features: assessment.features,
            last_result: {
              risk_tier: assessment.risk_tier,
              confidence: assessment.confidence,
              findings: assessment.findings,
              total_penalty_exposure_inr: assessment.total_penalty_exposure_inr,
              imprisonment_risk: assessment.imprisonment_risk,
              anomaly: { anomaly_summary: assessment.anomaly_summary },
              detected_flags: assessment.detected_flags,
            },
            last_flags: assessment.detected_flags,
            business_name: businessName || undefined,
            sector,
          }
        : {};
      const res: AgentResponse = await runAgent(msg, sessionContext);
      setMessages((m) => [...m, { role: "agent", content: res.reply, toolUsed: res.tool_used, confidence: res.confidence }]);
    } catch (e: any) {
      setMessages((m) => [...m, { role: "agent", content: `Error: ${e.message ?? "request failed"}` }]);
    } finally {
      setChatBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-cream-50">
      <Header />
      <main className="max-w-6xl mx-auto px-6 py-12">
        <div className="mb-10">
          <p className="font-body text-gold-500 text-sm tracking-widest uppercase mb-2">FinTriage AI · Agent Console</p>
          <h1 className="font-display text-4xl md:text-5xl text-brown-900 tracking-tight">
            Compliance triage, penalty exposure, and audit reports — in one conversation.
          </h1>
          <p className="font-body text-brown-700 mt-3 max-w-2xl">
            Describe an SME's transactions and onboarding profile. The pipeline runs anomaly
            detection, an XGBoost risk classifier, and a 40-rule compliance gap scorer —
            then the agent lets you ask "what if", simulate penalties, and generate a report.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
          {/* ── Left: intake + assessment result ─────────────────────────── */}
          <div className="lg:col-span-2 space-y-5">
            <div className="bg-stone-200/40 border border-brown-500/15 rounded-2xl p-6">
              <label className="font-body text-sm text-brown-700 mb-1 block">Business name (optional)</label>
              <input
                value={businessName}
                onChange={(e) => setBusinessName(e.target.value)}
                placeholder="e.g. Apex Textiles Pvt Ltd"
                className="w-full mb-4 rounded-lg border border-brown-500/25 bg-cream-100 px-3 py-2 font-body text-brown-900 placeholder:text-brown-500/50 focus:outline-none focus:ring-2 focus:ring-gold-500/40"
              />

              <label className="font-body text-sm text-brown-700 mb-1 block">Sector</label>
              <select
                value={sector}
                onChange={(e) => setSector(e.target.value)}
                className="w-full mb-4 rounded-lg border border-brown-500/25 bg-cream-100 px-3 py-2 font-body text-brown-900 focus:outline-none focus:ring-2 focus:ring-gold-500/40"
              >
                {["Trading", "Manufacturing", "IT Services", "NBFC", "Import/Export", "Real Estate", "Retail"].map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>

              <label className="font-body text-sm text-brown-700 mb-1 block">Describe the entity & transactions</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={7}
                placeholder={EXAMPLE_PROMPTS[0]}
                className="w-full rounded-lg border border-brown-500/25 bg-cream-100 px-3 py-2 font-body text-brown-900 placeholder:text-brown-500/40 focus:outline-none focus:ring-2 focus:ring-gold-500/40 resize-none"
              />

              <div className="flex gap-2 mt-2 flex-wrap">
                {EXAMPLE_PROMPTS.map((p, i) => (
                  <button
                    key={i}
                    onClick={() => setDescription(p)}
                    className="text-xs font-body text-brown-700 border border-brown-500/25 rounded-full px-3 py-1 hover:bg-gold-500/10 transition-colors"
                  >
                    Example {i + 1}
                  </button>
                ))}
              </div>

              <button
                onClick={handleAssess}
                disabled={assessing || !description.trim()}
                className="mt-4 w-full rounded-lg bg-brown-900 text-cream-50 font-body font-medium py-3 hover:bg-brown-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {assessing && <Loader2 className="w-4 h-4 animate-spin" />}
                {assessing ? "Running Stage 0 → 1 → 2/3…" : "Run Compliance Assessment"}
              </button>
              {assessError && <p className="text-error-500 text-sm font-body mt-2">{assessError}</p>}
            </div>

            {assessment && (
              <div className="bg-stone-200/40 border border-brown-500/15 rounded-2xl p-6">
                <div className="flex items-center justify-between mb-3">
                  <span className="font-display text-lg text-brown-900">Risk Assessment</span>
                  <span className={`text-xs font-medium font-body border rounded-full px-3 py-1 ${TIER_STYLES[assessment.risk_tier]}`}>
                    {assessment.risk_tier.toUpperCase()}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-3 font-body text-sm">
                  <div>
                    <p className="text-brown-500">Confidence</p>
                    <p className="text-brown-900 font-medium">{Math.round(assessment.confidence * 100)}%</p>
                  </div>
                  <div>
                    <p className="text-brown-500">Penalty exposure</p>
                    <p className="text-brown-900 font-medium">₹{Math.round(assessment.total_penalty_exposure_inr).toLocaleString("en-IN")}</p>
                  </div>
                  <div>
                    <p className="text-brown-500">Rules flagged</p>
                    <p className="text-brown-900 font-medium">{assessment.findings.length}</p>
                  </div>
                  <div>
                    <p className="text-brown-500">Imprisonment risk</p>
                    <p className="text-brown-900 font-medium">{assessment.imprisonment_risk ? "Yes" : "No"}</p>
                  </div>
                </div>

                {assessment.detected_flags.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {assessment.detected_flags.map((f) => (
                      <span key={f} className="text-[11px] font-body bg-brown-900/5 text-brown-700 rounded-full px-2 py-0.5 border border-brown-500/15">
                        {f.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}

                <div className="mt-4 space-y-2">
                  {assessment.findings.slice(0, 5).map((f) => (
                    <div key={f.rule_code} className="border border-brown-500/15 rounded-lg p-3 bg-cream-100/60">
                      <div className="flex justify-between items-start">
                        <span className="font-body font-medium text-brown-900 text-sm">{f.rule_code} — {f.rule_name}</span>
                        <span className={`text-[10px] uppercase font-medium border rounded-full px-2 py-0.5 ${TIER_STYLES[f.severity]}`}>{f.severity}</span>
                      </div>
                      <p className="font-body text-xs text-brown-700 mt-1">{f.description}</p>
                      <p className="font-body text-[11px] text-brown-500 mt-1">Max penalty ₹{f.max_penalty_inr.toLocaleString("en-IN")} · gap {Math.round(f.combined_score * 100)}%</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ── Right: agent chat (7 tools) ──────────────────────────────── */}
          <div className="lg:col-span-3 bg-brown-900 rounded-2xl p-6 flex flex-col h-[720px]">
            <div className="flex items-center justify-between mb-4">
              <span className="font-display text-lg text-cream-50">FinTriage Agent</span>
              <span className="font-body text-[11px] text-gold-500 tracking-wide uppercase">
                reassess · penalty_sim · threshold_sim · compare · explain_risk · rule_info · generate_report
              </span>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 pr-1">
              {messages.length === 0 && (
                <p className="font-body text-cream-50/40 text-sm">
                  Run an assessment on the left, then ask things like "why is this high risk?",
                  "what if cash ratio doubles?", "simulate the CTR penalty", or "generate a report".
                </p>
              )}
              {messages.map((m, i) => (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[85%] rounded-xl px-4 py-2.5 font-body text-sm whitespace-pre-wrap ${
                      m.role === "user" ? "bg-gold-500 text-brown-900" : "bg-cream-50/10 text-cream-50"
                    }`}
                  >
                    {m.content}
                    {m.toolUsed && (
                      <p className="text-[10px] uppercase tracking-wide mt-1.5 opacity-60">
                        {m.toolUsed} · {Math.round((m.confidence ?? 0) * 100)}% confidence
                      </p>
                    )}
                  </div>
                </div>
              ))}
              {chatBusy && (
                <div className="flex justify-start">
                  <div className="bg-cream-50/10 rounded-xl px-4 py-3 flex gap-1.5 items-center">
                    <span className="w-1.5 h-1.5 rounded-full bg-cream-50/50 animate-bounce [animation-delay:-0.3s]" />
                    <span className="w-1.5 h-1.5 rounded-full bg-cream-50/50 animate-bounce [animation-delay:-0.15s]" />
                    <span className="w-1.5 h-1.5 rounded-full bg-cream-50/50 animate-bounce" />
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            <div className="mt-4 flex gap-2">
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="Ask the agent…"
                className="flex-1 rounded-lg bg-cream-50/10 border border-cream-50/15 px-3 py-2.5 font-body text-cream-50 placeholder:text-cream-50/30 focus:outline-none focus:ring-2 focus:ring-gold-500/40"
              />
              <button
                onClick={handleSend}
                disabled={chatBusy || !chatInput.trim()}
                className="rounded-lg bg-gold-500 text-brown-900 font-body font-medium px-5 hover:bg-gold-500/90 transition-colors disabled:opacity-40"
              >
                Send
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
