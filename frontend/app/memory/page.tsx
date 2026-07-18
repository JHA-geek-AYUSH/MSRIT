"use client";

/**
 * Replaces the previous AgentOS "personal memory" page (facts/preferences stored
 * against a fake /api/memory route) — irrelevant to a compliance platform. This is
 * the real Platform Knowledge Base: local TF-IDF retrieval over Plan.md, the rule
 * catalogue, and penalty scenarios, synthesized by Gemma. See
 * backend/app/ml/knowledge_base.py and POST /v1/knowledge/ask.
 */

import { useState } from "react";
import { Header } from "@/components/layout/Header";
import { askKnowledgeBase } from "@/lib/compliance-api";

const EXAMPLE_QUESTIONS = [
  "How is the risk tier calculated?",
  "What happens if I don't file an STR in time?",
  "What is Rule AML-001?",
];

export default function KnowledgeBasePage() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<{ question: string; answer: string; sources: string[] }[]>([]);
  const [busy, setBusy] = useState(false);

  async function handleAsk(q?: string) {
    const query = (q ?? question).trim();
    if (!query || busy) return;
    setQuestion("");
    setBusy(true);
    try {
      const res = await askKnowledgeBase(query);
      setHistory((h) => [...h, { question: query, answer: res.answer, sources: res.sources }]);
    } catch (e: any) {
      setHistory((h) => [...h, { question: query, answer: `Error: ${e.message}`, sources: [] }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-cream-50">
      <Header />
      <main className="max-w-3xl mx-auto px-6 py-12">
        <p className="font-body text-gold-500 text-sm tracking-widest uppercase mb-2">Platform Knowledge Base</p>
        <h1 className="font-display text-4xl text-brown-900 mb-3">Ask anything about the platform</h1>
        <p className="font-body text-brown-700 mb-6">
          Retrieval-grounded answers from the rule catalogue, penalty scenarios, and platform documentation — synthesized by Gemma, not a general-purpose model.
        </p>

        <div className="flex gap-2 mb-3">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAsk()}
            placeholder="Ask a question…"
            className="flex-1 rounded-lg border border-brown-500/25 bg-cream-100 px-3 py-2.5 font-body text-brown-900 placeholder:text-brown-500/40 focus:outline-none focus:ring-2 focus:ring-gold-500/40"
          />
          <button
            onClick={() => handleAsk()}
            disabled={busy || !question.trim()}
            className="rounded-lg bg-brown-900 text-cream-50 font-body font-medium px-5 hover:bg-brown-700 transition-colors disabled:opacity-40"
          >
            Ask
          </button>
        </div>

        <div className="flex flex-wrap gap-2 mb-8">
          {EXAMPLE_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => handleAsk(q)}
              className="text-xs font-body text-brown-700 border border-brown-500/25 rounded-full px-3 py-1.5 hover:bg-gold-500/10 transition-colors"
            >
              {q}
            </button>
          ))}
        </div>

        <div className="space-y-4">
          {history.map((h, i) => (
            <div key={i} className="bg-stone-200/40 border border-brown-500/15 rounded-xl p-5">
              <p className="font-body font-medium text-brown-900 mb-2">{h.question}</p>
              <p className="font-body text-sm text-brown-700 whitespace-pre-wrap">{h.answer}</p>
              {h.sources.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {h.sources.map((s) => (
                    <span key={s} className="text-[10px] font-body bg-brown-900/5 text-brown-500 rounded-full px-2 py-0.5 border border-brown-500/15">
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
          {busy && <p className="font-body text-brown-500 text-sm">Searching…</p>}
        </div>
      </main>
    </div>
  );
}
