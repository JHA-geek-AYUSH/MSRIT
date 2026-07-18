"use client";

import { useEffect, useState } from "react";
import { getPenaltyScenarios, runPenaltySim, type PenaltyScenario } from "@/lib/compliance-api";
import { Calculator, AlertTriangle, Loader2, TrendingUp } from "lucide-react";

export default function PenaltySimPage() {
  const [scenarios, setScenarios] = useState<PenaltyScenario[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [days, setDays] = useState(30);
  const [repeat, setRepeat] = useState(false);
  const [factors, setFactors] = useState<string[]>([]);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPenaltyScenarios()
      .then((res) => {
        setScenarios(res.scenarios ?? []);
        if (res.scenarios?.length) setScenarioId(res.scenarios[0].id);
      })
      .catch(() => {/* non-critical */});
  }, []);

  const scenario = scenarios.find((s) => s.id === scenarioId);

  async function handleRun() {
    setBusy(true);
    setError(null);
    try {
      const res = await runPenaltySim({
        scenario_id: scenarioId,
        days_since_breach: days,
        repeat_offence: repeat,
        aggravating_factors: factors,
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message ?? "Simulation failed.");
    } finally {
      setBusy(false);
    }
  }

  function toggleFactor(f: string) {
    setFactors((prev) => (prev.includes(f) ? prev.filter((x) => x !== f) : [...prev, f]));
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <p className="font-body text-gold-600 text-xs tracking-widest uppercase font-semibold mb-1">Penalty Simulator</p>
        <h1 className="font-display text-2xl sm:text-3xl text-brown-900 font-bold mb-1">Estimate Regulatory Fine Exposure</h1>
        <p className="font-body text-sm text-brown-600 max-w-xl leading-relaxed">
          Select a violation scenario and configure parameters to calculate worst-case penalty exposure
          under Indian regulatory frameworks.
        </p>
      </div>

      {/* Config form */}
      <div className="rounded-2xl border border-stone-200 bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-stone-100 flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-stone-100 flex items-center justify-center">
            <Calculator size={13} className="text-brown-400" />
          </div>
          <h2 className="font-body text-sm font-semibold text-brown-900">Simulation Parameters</h2>
        </div>

        <div className="px-5 py-5 space-y-5">
          {/* Scenario select */}
          <div>
            <label className="font-body text-xs font-semibold text-brown-600 block mb-1.5">Violation Scenario</label>
            <select
              value={scenarioId}
              onChange={(e) => { setScenarioId(e.target.value); setFactors([]); }}
              className="w-full rounded-xl border border-stone-200 bg-cream-50 px-3.5 py-2.5 font-body text-sm text-brown-900 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400 transition-colors"
            >
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>{s.name} ({s.rule_code})</option>
              ))}
            </select>
            {scenario && (
              <p className="font-body text-xs text-brown-500 mt-1.5 leading-relaxed">{scenario.description}</p>
            )}
          </div>

          {/* Days + repeat */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="font-body text-xs font-semibold text-brown-600 block mb-1.5">Days Since Breach</label>
              <input
                type="number"
                value={days}
                min={1}
                onChange={(e) => setDays(Number(e.target.value))}
                className="w-full rounded-xl border border-stone-200 bg-cream-50 px-3.5 py-2.5 font-body text-sm text-brown-900 focus:outline-none focus:ring-2 focus:ring-gold-400/30 focus:border-gold-400 transition-colors"
              />
            </div>
            <div className="flex items-end pb-1">
              <label className="font-body text-sm text-brown-700 flex items-center gap-3 cursor-pointer">
                <div
                  onClick={() => setRepeat(!repeat)}
                  className={`w-10 h-5 rounded-full border transition-colors relative cursor-pointer ${repeat ? "bg-brown-900 border-brown-900" : "bg-stone-200 border-stone-300"}`}
                >
                  <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${repeat ? "translate-x-5" : "translate-x-0.5"}`} />
                </div>
                Repeat offence
              </label>
            </div>
          </div>

          {/* Aggravating factors */}
          {scenario && scenario.aggravating_factors?.length > 0 && (
            <div>
              <label className="font-body text-xs font-semibold text-brown-600 block mb-2">Aggravating Factors</label>
              <div className="flex flex-wrap gap-2">
                {scenario.aggravating_factors.map((f: string) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => toggleFactor(f)}
                    className={`font-body text-xs rounded-full px-3 py-1.5 border transition-colors ${
                      factors.includes(f)
                        ? "bg-brown-900 text-cream-50 border-brown-900"
                        : "bg-stone-50 text-brown-600 border-stone-200 hover:bg-stone-100 hover:border-stone-300"
                    }`}
                  >
                    {f.replace(/_/g, " ")}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-start gap-3 rounded-xl bg-red-50 border border-red-200 p-3">
              <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
              <p className="font-body text-sm text-red-700">{error}</p>
            </div>
          )}

          {/* Run button */}
          <button
            onClick={handleRun}
            disabled={busy || !scenarioId}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-brown-900 text-cream-50 font-body font-semibold py-3 hover:bg-brown-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {busy ? <><Loader2 className="w-4 h-4 animate-spin" /> Calculating…</> : <><TrendingUp className="w-4 h-4" /> Run Simulation</>}
          </button>
        </div>
      </div>

      {/* Result */}
      {result && (
        <div className="rounded-2xl border border-brown-900/10 bg-brown-900 p-6 shadow-lg">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <p className="font-body text-xs font-semibold text-cream-50/40 uppercase tracking-widest mb-1">Total Exposure</p>
              <p className="font-display text-4xl font-bold text-cream-50">
                ₹{result.total_fine.toLocaleString("en-IN")}
              </p>
            </div>
            {result.capped && (
              <span className="font-body text-[10px] font-semibold uppercase tracking-wide bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-full px-2.5 py-1">
                Capped
              </span>
            )}
          </div>

          <p className="font-body text-sm text-cream-50/70 mb-5 leading-relaxed">{result.verdict}</p>

          <div className="grid grid-cols-3 gap-4 pt-4 border-t border-cream-50/10">
            {[
              { label: "Base Fine", value: `₹${result.base_fine.toLocaleString("en-IN")}` },
              { label: "Time Penalty", value: `₹${result.time_penalty.toLocaleString("en-IN")}` },
              { label: "Multiplier", value: `${result.aggravating_multiplier}×` },
            ].map((stat) => (
              <div key={stat.label} className="text-center">
                <p className="font-display text-lg font-bold text-cream-50">{stat.value}</p>
                <p className="font-body text-[10px] text-cream-50/40 uppercase tracking-wide">{stat.label}</p>
              </div>
            ))}
          </div>

          {result.imprisonment_risk && (
            <div className="flex items-center gap-2 rounded-xl bg-red-900/30 border border-red-700/30 px-3 py-2.5 mt-4">
              <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
              <p className="font-body text-xs text-red-300">
                Imprisonment risk: up to {result.imprisonment_months} months
              </p>
            </div>
          )}

          {result.capped && (
            <p className="font-body text-xs text-amber-400/80 mt-3">
              Capped at statutory maximum: ₹{result.max_fine.toLocaleString("en-IN")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
