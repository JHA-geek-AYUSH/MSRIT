'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useAuth } from '@clerk/nextjs';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { runAssessment, runAgent, type AssessResponse, type AgentResponse } from '@/lib/compliance-api';
import { Loader2, Shield, AlertTriangle, CheckCircle, Activity, ArrowRight, Gauge, Scale, TrendingUp, Users, FileText, Sliders, Play, RefreshCw } from 'lucide-react';

// ── Sector options ──
const SECTORS = [
  { value: '', label: 'Select sector...' },
  { value: 'real_estate', label: 'Real Estate' },
  { value: 'crypto', label: 'Cryptocurrency / Virtual Assets' },
  { value: 'jewellery', label: 'Jewellery / Precious Metals' },
  { value: 'forex', label: 'Money Services / Forex' },
  { value: 'construction', label: 'Construction' },
  { value: 'retail', label: 'Retail (Cash-heavy)' },
  { value: 'manufacturing', label: 'Manufacturing' },
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'it', label: 'IT / Software Services' },
  { value: 'education', label: 'Education' },
];

// ── Example cases ──
const EXAMPLES = [
  {
    name: 'Suspicious Cash Transactions',
    business_name: 'Apex Realty Pvt Ltd',
    sector: 'real_estate',
    description: 'Customer deposited ₹9.8L in cash three times over 5 days to three different accounts across different cities. The company has only 1 director, no employees, and has been dormant for 8 months before this sudden activity.',
  },
  {
    name: 'PEP Onboarding Risk',
    business_name: 'Global Trade Ventures',
    sector: 'forex',
    description: 'New corporate client requesting account opening. One director is a politically exposed person (PEP) with government connections. UBO declaration missing. No supporting documents for beneficial ownership verification.',
  },
  {
    name: 'Financially Distressed SME',
    business_name: 'CityMart Retail Chain',
    sector: 'retail',
    description: 'SME with ₹2.4Cr annual turnover showing 60-day overdue invoices totalling ₹45L. Debt-to-equity ratio is 3:1. No credit insurance. 80% of revenue comes from a single supplier. Late GST filing by 45 days.',
  },
];

// ── Agent definitions ──
const AGENTS = [
  { id: 'anomaly', label: 'Anomaly Detection', icon: AlertTriangle, color: 'from-red-500 to-red-600', desc: 'Scanning for suspicious patterns...' },
  { id: 'risk', label: 'Risk Classification', icon: Gauge, color: 'from-orange-500 to-orange-600', desc: 'Running XGBoost classifier...' },
  { id: 'compliance', label: 'Compliance Scoring', icon: Scale, color: 'from-amber-500 to-amber-600', desc: 'Scoring against 40 rules...' },
  { id: 'financial', label: 'Financial Analysis', icon: TrendingUp, color: 'from-teal-500 to-teal-600', desc: 'Assessing financial health...' },
  { id: 'report', label: 'Report Synthesis', icon: FileText, color: 'from-violet-500 to-violet-600', desc: 'Generating compliance report...' },
];

// ── Risk colors ──
const RISK_COLORS: Record<string, { bg: string; border: string; text: string; gauge: string; light: string }> = {
  critical: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', gauge: 'stroke-red-500', light: 'from-red-50 to-red-50/30' },
  high: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700', gauge: 'stroke-orange-500', light: 'from-orange-50 to-orange-50/30' },
  medium: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', gauge: 'stroke-amber-500', light: 'from-amber-50 to-amber-50/30' },
  low: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', gauge: 'stroke-emerald-500', light: 'from-emerald-50 to-emerald-50/30' },
};

// ── Risk Gauge Component ──
function RiskGauge({ tier, confidence }: { tier: string; confidence: number }) {
  const color = RISK_COLORS[tier] || RISK_COLORS.medium;
  const pct = Math.round(confidence * 100);
  const degrees = (() => {
    if (tier === 'critical') return 180 + (pct / 100) * 180;
    if (tier === 'high') return 135 + (pct / 100) * 90;
    if (tier === 'medium') return 45 + (pct / 100) * 90;
    return 0 + (pct / 100) * 90;
  })();

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-32 h-32">
        <svg className="w-32 h-32 -rotate-90" viewBox="0 0 120 120">
          {/* Background arc */}
          <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" strokeWidth="8" className="text-stone-200" />
          {/* Fill arc */}
          <circle
            cx="60" cy="60" r="52"
            fill="none"
            strokeWidth="8"
            strokeLinecap="round"
            className={color.gauge}
            strokeDasharray={`${(degrees / 360) * 327} 327`}
            style={{ transition: 'stroke-dasharray 1s ease-out' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn('text-2xl font-bold', color.text)}>
            {tier === 'critical' ? '🚨' : tier === 'high' ? '🔴' : tier === 'medium' ? '🟡' : '🟢'}
          </span>
          <span className={cn('text-[10px] font-semibold uppercase mt-0.5', color.text)}>{tier}</span>
        </div>
      </div>
      <div className="flex items-center gap-1.5 mt-1">
        <span className="text-[10px] text-zinc-400">Confidence</span>
        <span className="text-xs font-semibold text-zinc-700 text-brown-700">{pct}%</span>
      </div>
    </div>
  );
}

// ── Main Page ──
export default function CompliancePage() {
  const { isLoaded, isSignedIn } = useAuth();

  // Form state
  const [businessName, setBusinessName] = useState('');
  const [sector, setSector] = useState('');
  const [description, setDescription] = useState('');
  const [showExamples, setShowExamples] = useState(false);

  // Pipeline state
  const [phase, setPhase] = useState<'input' | 'running' | 'results' | 'whatif'>('input');
  const [loading, setLoading] = useState(false);
  const [agentStep, setAgentStep] = useState(0);
  const [agentLog, setAgentLog] = useState<string[]>([]);
  const [result, setResult] = useState<AssessResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Chat state (declare BEFORE effects that reference them)
  const [chatMessages, setChatMessages] = useState<{ role: string; content: string; data?: any }[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatInputRef = useRef('');
  const chatRef = useRef<HTMLDivElement>(null);

  // Keep chatInputRef in sync
  useEffect(() => { chatInputRef.current = chatInput; }, [chatInput]);

  // What-if state
  const [whatIfFeatures, setWhatIfFeatures] = useState<Record<string, number>>({});
  const [whatIfResult, setWhatIfResult] = useState<AssessResponse | null>(null);
  const [whatIfLoading, setWhatIfLoading] = useState(false);

  // Cleanup on unmount
  useEffect(() => () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  }, []);
  useEffect(() => { chatRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chatMessages, chatLoading]);

  // ── Run Assessment ──
  const handleRun = useCallback(async () => {
    if (!description.trim()) return;
    setLoading(true);
    setPhase('running');
    setError(null);
    setResult(null);
    setAgentStep(0);
    setAgentLog([]);
    setWhatIfResult(null);
    setChatMessages([{ role: 'agent', content: 'Analysis complete! Ask me about the risks, simulate penalties, or compare scenarios.' }]);

    // Animate agents
    const logMessages = [
      '🔍 Scanning transaction patterns for AML/CFT indicators...',
      '📊 Running XGBoost risk classifier on 9 financial features...',
      '⚖️ Scoring against 40 compliance rules across 6 frameworks...',
      '📈 Calculating credit, market, and liquidity risk metrics...',
      '📄 Synthesizing findings into compliance report...',
    ];
    intervalRef.current = setInterval(() => {
      setAgentStep(prev => {
        if (prev >= AGENTS.length) return prev;
        setAgentLog(l => [...l, logMessages[prev]]);
        return prev + 1;
      });
    }, 800);

    try {
      const data = await runAssessment({
        business_name: businessName || undefined,
        sector: sector || undefined,
        description,
      });
      setResult(data);
      setWhatIfFeatures({ ...data.features });
      setAgentStep(AGENTS.length);
      setAgentLog(l => [...l, 'Assessment complete. Showing results.']);
      // Do not defer this transition: the finally block below clears pending
      // timers, which previously left the UI stuck on the completed pipeline.
      setPhase('results');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Assessment failed.');
      setPhase('input');
    } finally {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = null;
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
      setLoading(false);
    }
  }, [businessName, sector, description]);

  // ── What-If Analysis ──
  const handleWhatIf = useCallback(async () => {
    if (!whatIfFeatures) return;
    setWhatIfLoading(true);
    try {
      const data = await runAssessment({
        features: whatIfFeatures,
        sector: sector || undefined,
      });
      setWhatIfResult(data);
    } catch (err: unknown) {
      console.error('What-if failed:', err);
    } finally {
      setWhatIfLoading(false);
    }
  }, [whatIfFeatures, sector]);

  // ── Chat ──
  const handleChat = useCallback(async () => {
    const msg = chatInputRef.current;
    if (!msg.trim() || chatLoading || !result) return;
    setChatInput('');
    chatInputRef.current = '';
    setChatMessages(p => [...p, { role: 'user', content: msg }]);
    setChatLoading(true);
    try {
      const ctx: Record<string, any> = {
        last_features: result.features,
        last_result: result,
        last_flags: result.detected_flags,
        business_name: businessName,
        sector,
      };
      const res = await runAgent(msg, ctx);
      setChatMessages(p => [...p, { role: 'agent', content: res.reply, data: res.data }]);
    } catch (err: any) {
      setChatMessages(p => [...p, { role: 'agent', content: `Error: ${err.message}` }]);
    } finally {
      setChatLoading(false);
    }
  }, [chatLoading, result, businessName, sector]);

  // ── Reset ──
  const handleReset = useCallback(() => {
    setPhase('input');
    setResult(null);
    setError(null);
    setWhatIfResult(null);
    setChatMessages([]);
    setAgentLog([]);
  }, []);

  // ── Render ──
  if (!isLoaded) return <div className="flex items-center justify-center min-h-[60vh]"><Loader2 className="h-6 w-6 animate-spin text-gold-600" /></div>;
  if (!isSignedIn) return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center max-w-sm"><Shield className="h-12 w-12 text-zinc-300 mx-auto mb-4" /><p className="text-sm text-zinc-500 mb-4">Sign in to run compliance assessments.</p><Link href="/sign-in" className="text-gold-600 font-medium text-sm">Sign In →</Link></div>
    </div>
  );

  const tierColors = result ? RISK_COLORS[result.risk_tier] : RISK_COLORS.medium;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* ── Phase: Input ── */}
      {(phase === 'input' || phase === 'running') && (
        <>
          {/* Header */}
          <div className="rounded-2xl border border-stone-200 bg-cream-100/60 p-5">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-xl bg-gold-500/15 flex items-center justify-center shrink-0">
                <Shield className="w-5 h-5 text-gold-600" />
              </div>
              <div>
                <h2 className="font-semibold text-sm text-brown-900">Financial Compliance Risk Assessment</h2>
                <p className="text-xs text-brown-600 mt-1 leading-relaxed">
                  Describe a business entity or transaction case. Our <strong>multi-agent pipeline</strong> (XGBoost + 40 compliance rules)
                  will assess risk across <strong>6 Indian regulatory frameworks</strong>: PMLA, FEMA, RBI KYC, GST, Income Tax, Companies Act.
                </p>
              </div>
            </div>
          </div>

          {/* Form */}
          <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="text-xs font-medium text-zinc-600 text-brown-600 mb-1 block">Business Name</label>
                <input
                  value={businessName}
                  onChange={e => setBusinessName(e.target.value)}
                  placeholder="e.g. Apex Realty Pvt Ltd"
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-500/30 focus:border-gold-500"
                  disabled={loading}
                />
              </div>
              <div>
                <label className="text-xs font-medium text-zinc-600 text-brown-600 mb-1 block">Sector</label>
                <select
                  value={sector}
                  onChange={e => setSector(e.target.value)}
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-500/30 focus:border-gold-500"
                  disabled={loading}
                >
                  {SECTORS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </div>
            </div>

            <label className="text-xs font-medium text-zinc-600 text-brown-600 mb-1 block">Transaction / Entity Description</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={4}
              placeholder="Describe the business activities, transactions, or compliance case..."
              className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-gold-500/30 focus:border-gold-500 mb-3"
              disabled={loading}
            />

            <div className="flex items-center justify-between mb-4">
              <button onClick={() => setShowExamples(!showExamples)} className="text-[11px] text-gold-600 hover:text-gold-700">{showExamples ? 'Hide' : 'Load'} example cases</button>
              <span className={cn("text-[10px] font-mono", description.length < 10 && description.length > 0 ? "text-red-400" : "text-zinc-400")}>{description.length} chars</span>
            </div>

            {showExamples && (
              <div className="space-y-2 mb-4">
                {EXAMPLES.map((ex, i) => (
                  <button
                    key={i}
                    onClick={() => { setBusinessName(ex.business_name); setSector(ex.sector); setDescription(ex.description); }}
                    className="block w-full text-left text-xs text-zinc-600 text-brown-600 bg-zinc-50  rounded-lg px-3 py-2.5 border border-zinc-100  hover:border-gold-500/30 hover:text-gold-700 transition-colors leading-relaxed"
                  >
                    <span className="font-medium text-zinc-800 text-brown-800">{ex.name}</span>: {ex.description.slice(0, 100)}...
                  </button>
                ))}
              </div>
            )}

            <button
              onClick={handleRun}
              disabled={loading || description.trim().length < 10}
              className={cn(
                "w-full rounded-xl font-semibold py-2.5 text-sm transition-all flex items-center justify-center gap-2",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                "bg-brown-900 hover:bg-brown-800 text-cream-50 shadow-sm hover:shadow-md",
                !loading && "hover:-translate-y-0.5 active:scale-[0.99]",
              )}
            >
              {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Running...</> : <><Play className="w-4 h-4" /> Run Assessment</>}
            </button>
          </div>
        </>
      )}

      {/* ── Phase: Running (Agent Orchestration) ── */}
      {phase === 'running' && (
        <div className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-5">
            <div className="w-3 h-3 rounded-full bg-gold-500 animate-pulse" />
            <h3 className="font-semibold text-sm text-zinc-800 text-brown-800">Multi-Agent Pipeline Running</h3>
            <span className="ml-auto text-[10px] text-zinc-400 bg-zinc-100 bg-stone-100 px-2 py-0.5 rounded">{agentStep}/{AGENTS.length} complete</span>
          </div>

          {/* Agent progress */}
          <div className="grid grid-cols-5 gap-2 mb-5">
            {AGENTS.map((agent, idx) => {
              const AgentIcon = agent.icon;
              const status = idx < agentStep ? 'done' : idx === agentStep ? 'current' : 'pending';
              return (
                <div key={agent.id} className={cn(
                  "flex flex-col items-center gap-2 p-3 rounded-xl border transition-all duration-500",
                  status === 'done' && "bg-emerald-50 border-emerald-200",
                  status === 'current' && "bg-gold-500/10 border-gold-500/30 ring-2 ring-gold-500/30 animate-pulse",
                  status === 'pending' && "bg-zinc-50  border-zinc-100  opacity-40",
                )}>
                  <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center", status === 'done' ? "bg-emerald-100 dark:bg-emerald-900/50" : status === 'current' ? "bg-gold-500/20" : "bg-zinc-100 bg-stone-100")}>
                    {status === 'done' ? <CheckCircle className="w-4 h-4 text-emerald-600" /> : <AgentIcon className={cn("w-4 h-4", status === 'current' ? "text-gold-600" : "text-zinc-400")} />}
                  </div>
                  <span className={cn("text-[10px] font-medium text-center", status === 'done' && "text-emerald-700", status === 'current' && "text-gold-700", status === 'pending' && "text-zinc-400")}>{agent.label}</span>
                </div>
              );
            })}
          </div>

          {/* Live log */}
          <div className="rounded-xl bg-zinc-900  p-4 max-h-[200px] overflow-y-auto font-mono text-xs space-y-1.5">
            {agentLog.map((log, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-emerald-400 shrink-0">→</span>
                <span className={cn(i === agentLog.length - 1 && agentStep < AGENTS.length ? 'text-gold-400 animate-pulse' : 'text-zinc-300')}>{log}</span>
              </div>
            ))}
            {agentLog.length === 0 && <span className="text-zinc-600">Initializing agents...</span>}
          </div>
        </div>
      )}

      {/* ── Phase: Results ── */}
      {phase === 'results' && result && (
        <div className="space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
          {/* Top: Risk Gauge + Key Metrics */}
          <div className={cn("rounded-2xl border p-6 shadow-sm bg-gradient-to-br", tierColors.light)}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-zinc-800 text-brown-800">Assessment Results</h3>
              <div className="flex gap-2">
                <button onClick={() => setPhase('input')} className="text-[10px] text-zinc-400 hover:text-zinc-600 bg-white bg-stone-100 px-2.5 py-1 rounded-lg border border-zinc-200  hover:border-gold-500/30 transition-colors flex items-center gap-1">
                  <RefreshCw className="w-3 h-3" /> New
                </button>
                <button onClick={() => setPhase('whatif')} className="text-[10px] text-gold-600 hover:text-gold-700 bg-gold-500/10 px-2.5 py-1 rounded-lg border border-gold-500/30 transition-colors flex items-center gap-1">
                  <Sliders className="w-3 h-3" /> What-If
                </button>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-6">
              <RiskGauge tier={result.risk_tier} confidence={result.confidence} />
              <div className="flex-1 grid grid-cols-2 sm:grid-cols-3 gap-4 w-full">
                <MetricCard label="Risk Tier" value={result.risk_tier.toUpperCase()} color={tierColors.text} />
                <MetricCard label="Confidence" value={`${Math.round(result.confidence * 100)}%`} />
                <MetricCard label="Rules Flagged" value={`${result.findings.length}`} />
                <MetricCard label="Penalty Exposure" value={`₹${Math.round(result.total_penalty_exposure_inr).toLocaleString('en-IN')}`} highlight />
                <MetricCard label="Flags Detected" value={`${result.detected_flags.length}`} />
                <MetricCard label="Imprisonment Risk" value={result.imprisonment_risk ? '⚠ YES' : 'No'} color={result.imprisonment_risk ? 'text-red-500' : 'text-emerald-500'} />
              </div>
            </div>

            {/* STR/EDD banners */}
            {result.auto_escalated && (
              <div className="mt-4 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-3">
                <AlertTriangle className="w-5 h-5 text-red-500 mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs font-bold text-red-700">Auto-Escalated — PEP or Shell Company Detected</p>
                  <p className="text-[10px] text-red-600 dark:text-red-400 mt-0.5">Critical risk tier applied regardless of ML score due to high-risk indicators.</p>
                </div>
              </div>
            )}
          </div>

          {/* Findings */}
          <div>
            <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <AlertTriangle className="w-3 h-3" />
              Top Compliance Findings ({result.findings.length})
            </h4>
            <div className="space-y-2">
              {result.findings.slice(0, 6).map((f, i) => (
                <div key={i} className={cn(
                  "rounded-xl border p-4 bg-white bg-white shadow-sm transition-all hover:shadow-md",
                  f.severity === 'critical' && "border-red-200",
                  f.severity === 'high' && "border-orange-200",
                  f.severity === 'medium' && "border-amber-200",
                  f.severity === 'low' && "border-zinc-200 ",
                )}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={cn(
                          "text-[10px] font-bold uppercase px-2 py-0.5 rounded-full",
                          f.severity === 'critical' && "bg-red-100 text-red-700 dark:bg-red-900/50",
                          f.severity === 'high' && "bg-orange-100 text-orange-700 dark:bg-orange-900/50",
                          f.severity === 'medium' && "bg-amber-100 text-amber-700 dark:bg-amber-900/50",
                          f.severity === 'low' && "bg-zinc-100 text-zinc-600 bg-stone-100 text-brown-600",
                        )}>{f.severity}</span>
                        <span className="text-xs font-semibold text-zinc-800 text-brown-800">{f.rule_code}</span>
                      </div>
                      <p className="text-xs text-zinc-600 text-brown-600 mt-2 leading-relaxed">{f.description}</p>
                      {f.remediation_steps && f.remediation_steps.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {f.remediation_steps.slice(0, 2).map((step, j) => (
                            <span key={j} className="text-[10px] text-gold-600 bg-gold-500/10 px-2 py-0.5 rounded-full border border-gold-500/30">
                              {step}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-[10px] text-zinc-400">Score</p>
                      <p className="text-xs font-semibold text-zinc-700 text-brown-700">{Math.round(f.combined_score * 100)}%</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Agent Chat */}
          <div>
            <h4 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <Users className="w-3 h-3" />
              AI Compliance Analyst — Ask follow-up questions
            </h4>
            <div className="rounded-xl border border-stone-200 bg-white shadow-sm overflow-hidden">
              <div className="max-h-[300px] overflow-y-auto p-4 space-y-3">
                {chatMessages.map((m, i) => (
                  <div key={i} className={cn("flex", m.role === 'user' ? 'justify-end' : 'justify-start')}>
                    {m.role === 'agent' && <div className="w-6 h-6 rounded-full bg-gradient-to-br from-gold-500 to-gold-600 flex items-center justify-center text-[10px] mr-2 mt-0.5 shrink-0">🤖</div>}
                    <div className={cn(
                      "max-w-[80%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed shadow-sm",
                      m.role === 'user'
                        ? 'bg-gradient-to-br from-brown-800 to-brown-900 text-cream-50 rounded-br-md'
                        : 'bg-zinc-100 bg-stone-100 text-zinc-800 text-brown-800 rounded-bl-md border border-zinc-200/50 '
                    )}>
                      {m.role === 'agent' ? (
                        <span dangerouslySetInnerHTML={{ __html: m.content.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold">$1</strong>').replace(/\n/g, '<br/>') }} />
                      ) : m.content}
                    </div>
                  </div>
                ))}
                {chatLoading && (
                  <div className="flex justify-start">
                    <div className="w-6 h-6 rounded-full bg-gradient-to-br from-gold-500 to-gold-600 flex items-center justify-center text-[10px] mr-2 shrink-0">🤖</div>
                    <div className="bg-zinc-100 bg-stone-100 rounded-2xl rounded-bl-md px-4 py-3 border border-zinc-200/50 ">
                      <div className="flex gap-1"><span className="w-2 h-2 rounded-full bg-zinc-400 animate-bounce" style={{ animationDelay: '0ms' }} /><span className="w-2 h-2 rounded-full bg-zinc-400 animate-bounce" style={{ animationDelay: '150ms' }} /><span className="w-2 h-2 rounded-full bg-zinc-400 animate-bounce" style={{ animationDelay: '300ms' }} /></div>
                    </div>
                  </div>
                )}
                <div ref={chatRef} />
              </div>
              <div className="p-3 border-t border-zinc-200  bg-zinc-50  flex gap-2">
                <input
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleChat(); } }}
                  placeholder="Ask: what-if cash ratio doubles? simulate penalty? explain risk?"
                  className="flex-1 text-sm bg-white  border border-zinc-300  rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-gold-500/30 focus:border-gold-500"
                  disabled={chatLoading}
                />
                <button onClick={handleChat} disabled={chatLoading || !chatInput.trim()} className="bg-brown-900 hover:bg-brown-800 text-cream-50 px-5 py-2.5 rounded-xl text-sm font-medium transition-all shadow-sm disabled:opacity-50 active:scale-[0.97]">Send</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Phase: What-If Analysis ── */}
      {phase === 'whatif' && result && (
        <div className="space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-zinc-800 text-brown-800 flex items-center gap-2">
              <Sliders className="w-4 h-4 text-gold-600" />
              What-If Analysis
            </h3>
            <button onClick={() => setPhase('results')} className="text-[10px] text-zinc-400 hover:text-zinc-600 bg-white bg-stone-100 px-2.5 py-1 rounded-lg border border-zinc-200  transition-colors">← Back to Results</button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Sliders */}
            <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm space-y-4">
              <p className="text-xs text-zinc-500 mb-2">Adjust risk factors and see how the score changes</p>
              {whatIfFeatures && Object.entries(whatIfFeatures).filter(([k]) => ['cash_ratio','monthly_txn_volume','cross_border_ratio','anomaly_risk_score','director_count','avg_ticket_size','late_payment_rate'].includes(k)).map(([key, val]) => {
                const max = key.endsWith('ratio') || key === 'cash_ratio' || key === 'cross_border_ratio' || key === 'late_payment_rate' ? 1 : key === 'anomaly_risk_score' ? 5 : key === 'director_count' ? 10 : key === 'sector_risk_score' ? 1 : 1000;
                const step = key.endsWith('ratio') || key === 'anomaly_risk_score' || key === 'sector_risk_score' ? 0.05 : key === 'director_count' ? 1 : 10;
                return (
                  <div key={key}>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">{key.replace(/_/g, ' ')}</label>
                      <span className="text-xs font-mono text-zinc-700 text-brown-700">{typeof val === 'number' ? val.toFixed(2) : val}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max={max}
                      step={step}
                      value={val}
                      onChange={e => setWhatIfFeatures(p => ({ ...p, [key]: parseFloat(e.target.value) }))}
                      className="w-full h-1.5 rounded-full appearance-none bg-zinc-200 dark:bg-zinc-700 accent-gold-600 cursor-pointer"
                    />
                  </div>
                );
              })}

              <button
                onClick={handleWhatIf}
                disabled={whatIfLoading}
                className="w-full rounded-lg bg-brown-900 text-cream-50 text-sm font-medium py-2.5 hover:bg-brown-800 transition-all disabled:opacity-50 shadow-sm flex items-center justify-center gap-2"
              >
                {whatIfLoading ? <><Loader2 className="w-4 h-4 animate-spin" /> Recalculating...</> : <><RefreshCw className="w-4 h-4" /> Recalculate Risk</>}
              </button>
            </div>

            {/* Compare */}
            <div className="space-y-4">
              {/* Baseline */}
              <div className={cn("rounded-xl border p-5 shadow-sm", RISK_COLORS[result.risk_tier].light, RISK_COLORS[result.risk_tier].border)}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-zinc-600">Baseline</span>
                  <span className={cn("text-xs font-bold", RISK_COLORS[result.risk_tier].text)}>{result.risk_tier.toUpperCase()}</span>
                </div>
                <p className="text-xs text-zinc-500">{result.findings.length} rules · ₹{Math.round(result.total_penalty_exposure_inr).toLocaleString('en-IN')} exposure</p>
              </div>

              {/* Simulated */}
              {whatIfResult && (
                <div className={cn("rounded-xl border p-5 shadow-sm animate-in fade-in slide-in-from-right-2 duration-300", RISK_COLORS[whatIfResult.risk_tier].light, RISK_COLORS[whatIfResult.risk_tier].border)}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-zinc-600">Simulated</span>
                    <span className={cn("text-xs font-bold", RISK_COLORS[whatIfResult.risk_tier].text)}>{whatIfResult.risk_tier.toUpperCase()}</span>
                  </div>
                  <p className="text-xs text-zinc-500">{whatIfResult.findings.length} rules · ₹{Math.round(whatIfResult.total_penalty_exposure_inr).toLocaleString('en-IN')} exposure</p>
                  {result.risk_tier !== whatIfResult.risk_tier && (
                    <div className="mt-2 flex items-center gap-1 text-[10px] text-gold-600 bg-gold-500/10 px-2 py-1 rounded-full w-fit">
                      <TrendingUp className="w-3 h-3" />
                      Risk changed from {result.risk_tier.toUpperCase()} to {whatIfResult.risk_tier.toUpperCase()}
                    </div>
                  )}
                </div>
              )}

              {!whatIfResult && !whatIfLoading && (
                <div className="rounded-xl border border-dashed border-zinc-200  p-8 text-center">
                  <p className="text-xs text-zinc-400">Adjust the sliders and click "Recalculate" to see the impact</p>
                </div>
              )}

              {whatIfLoading && (
                <div className="rounded-xl border border-zinc-200  p-8 text-center">
                  <Loader2 className="w-5 h-5 animate-spin text-gold-600 mx-auto" />
                  <p className="text-xs text-zinc-400 mt-2">Recalculating...</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Error ── */}
      {error && (
        <div className="rounded-2xl border border-red-200 bg-gradient-to-br from-red-50 to-red-50/50 p-5">
          <div className="flex items-start gap-3"><AlertTriangle className="w-5 h-5 text-red-500 mt-0.5 shrink-0" /><div><p className="text-sm font-semibold text-red-800">Assessment Failed</p><p className="text-sm text-red-600 dark:text-red-400 mt-1">{error}</p></div></div>
        </div>
      )}

      {/* ── Empty state (no phase active) ── */}
      {phase === 'input' && !loading && !error && (
        <div className="text-center py-16">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-gold-500/10 to-gold-500/20 flex items-center justify-center mx-auto mb-4"><Shield className="w-8 h-8 text-gold-500" /></div>
          <p className="text-sm font-medium text-zinc-700 text-brown-700 mb-1">Enter business details above to start</p>
          <p className="text-xs text-zinc-400 max-w-md mx-auto leading-relaxed">Or click <strong>"Load example cases"</strong> for pre-written scenarios.</p>
        </div>
      )}
    </div>
  );
}

// ── Metric Card ──
function MetricCard({ label, value, color, highlight }: { label: string; value: string; color?: string; highlight?: boolean }) {
  return (
    <div className={cn("rounded-xl border p-3 bg-white bg-white", highlight ? "border-amber-200 bg-amber-50/50 dark:bg-amber-950/20" : "border-zinc-100 ")}>
      <p className="text-[10px] text-zinc-400 text-brown-500 uppercase tracking-wider">{label}</p>
      <p className={cn("text-sm font-bold mt-0.5", color || "text-zinc-800 text-brown-800")}>{value}</p>
    </div>
  );
}

