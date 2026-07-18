'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useUser } from '@clerk/nextjs';
import { ChatHeader } from '@/components/chat/ChatHeader';
import { ChatInput } from '@/components/chat/ChatInput';
import { MessageBubble } from '@/components/chat/MessageBubble';
import type { ChatMessage } from '@/types/chat';
import { runComplianceTriage } from '@/lib/database';
import { generateId } from '@/lib/utils';

export type Message = ChatMessage;

const SESSION_KEY = 'gemmaFin_chat_history';

const SUGGESTED_PROMPTS = [
  'Analyze this transaction for AML compliance: Customer deposited ₹9.8L three times in 5 days to different accounts',
  'Run full compliance check on a new corporate client with PEP directors',
  'Assess financial risk: SME with ₹2.4Cr turnover, 60-day overdue invoices of ₹45L',
  'Check regulatory compliance for a cross-border transaction of $50,000',
  'What are the PMLA 2002 obligations for reporting suspicious transactions?',
  'Summarize the latest SEBI guidelines on insider trading',
];

export default function ChatPage() {
  const { user, isLoaded } = useUser();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load chat history
  useEffect(() => {
    if (isLoaded && user) {
      const stored = sessionStorage.getItem(`${SESSION_KEY}_${user.id}`);
      if (stored) {
        try {
          const parsed = JSON.parse(stored);
          setMessages(parsed);
        } catch {
          setMessages([]);
        }
      }
    }
  }, [isLoaded, user]);

  // Persist messages
  useEffect(() => {
    if (user && messages.length > 0) {
      sessionStorage.setItem(`${SESSION_KEY}_${user.id}`, JSON.stringify(messages));
    }
  }, [messages, user]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  const handleClear = () => {
    if (user) sessionStorage.removeItem(`${SESSION_KEY}_${user.id}`);
    setMessages([]);
    setShowSuggestions(true);
  };

  const handleNew = () => {
    handleClear();
  };

  const handleSend = async (text: string) => {
    if (!text.trim() || isThinking) return;

    // Add user message
    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: text,
      status: 'done',
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    setShowSuggestions(false);

    // Thinking placeholder
    const thinkingId = generateId();
    const thinkingMsg: ChatMessage = {
      id: thinkingId,
      role: 'agent',
      content: '',
      status: 'thinking',
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, thinkingMsg]);
    setIsThinking(true);

    try {
      // Detect intent: compliance check, legal query, or general
      const lower = text.toLowerCase();
      const isCompliance = /compliance|aml|kyc|pmla|str|edd|transaction|regulatory|financial risk|audit|onboarding/i.test(lower);
      const isLegal = /statute|precedent|section|case|judgment|court|IPC|constitution/i.test(lower);

      if (isCompliance) {
        await handleComplianceQuery(text, thinkingId);
      } else {
        await handleGeneralQuery(text, thinkingId);
      }
    } catch (error) {
      console.error('[Chat] Error:', error);
      setMessages(prev => prev.map(m =>
        m.id === thinkingId
          ? { ...m, content: 'Sorry, I encountered an error processing your request. Please try again.', status: 'error' }
          : m,
      ));
    } finally {
      setIsThinking(false);
    }
  };

  const handleComplianceQuery = async (text: string, thinkingId: string) => {
    // Update to show initial thinking
    setMessages(prev => prev.map(m =>
      m.id === thinkingId ? { ...m, content: 'Running compliance triage...', status: 'streaming' } : m,
    ));

    // Add tool execution card
    const toolExecs = [
      { tool: 'Transaction Agent', description: 'Analyzing transaction patterns...', status: 'running' as const },
      { tool: 'Regulatory Agent', description: 'Checking compliance frameworks...', status: 'running' as const },
      { tool: 'Financial Risk Agent', description: 'Assessing risk profile...', status: 'running' as const },
    ];
    setMessages(prev => prev.map(m =>
      m.id === thinkingId ? { ...m, toolExecutions: toolExecs, content: 'Running compliance agents in parallel...' } : m,
    ));

    try {
      const result = await runComplianceTriage({ description: text });

      // Build a summary response
      const summary = [
        `## Compliance Triage Complete\n`,
        `**Overall Rating:** ${result.overall_rating.toUpperCase()}\n`,
        `**STR Required:** ${result.requires_str ? '⚠️ Yes' : 'No'}`,
        `**EDD Required:** ${result.requires_edd ? '⚠️ Yes' : 'No'}\n`,
        result.recommendations.length > 0 ? `\n**Key Recommendations:**\n${result.recommendations.slice(0, 3).map((r, i) => `${i + 1}. ${r}`).join('\n')}` : '',
      ].join('\n');

      // Mark tools as done
      const completedExecs = toolExecs.map(t => ({ ...t, status: 'done' as const }));

      setMessages(prev => prev.map(m =>
        m.id === thinkingId
          ? {
              ...m,
              content: summary,
              status: 'done',
              toolExecutions: completedExecs,
              complianceResult: result,
            }
          : m,
      ));
    } catch (error) {
      setMessages(prev => prev.map(m =>
        m.id === thinkingId
          ? { ...m, content: 'Compliance analysis failed. Please check your backend connection.', status: 'error' }
          : m,
      ));
    }
  };

  const handleGeneralQuery = async (text: string, thinkingId: string) => {
    // Simulate thinking with progressive updates
    const stages = [
      { content: 'Analyzing your query...', delay: 500 },
      { content: 'Searching knowledge base...', delay: 1500 },
      { content: 'Generating response...', delay: 2500 },
    ];

    for (const stage of stages) {
      await new Promise(r => setTimeout(r, stage.delay));
      setMessages(prev => prev.map(m =>
        m.id === thinkingId ? { ...m, content: stage.content } : m,
      ));
    }

    // Generate response based on keywords
    const lower = text.toLowerCase();
    let response = '';

    if (lower.includes('hello') || lower.includes('hi') || lower.includes('hey')) {
      response = `Hello! I'm GemmaFinOS, your AI-powered legal and compliance assistant. I can help you with:

• **Legal Research** — Statutes, precedents, case analysis
• **Compliance Checks** — AML/KYC, regulatory frameworks
• **Risk Assessment** — Financial, operational, legal risk
• **Document Analysis** — Contracts, agreements, policies
• **Investigations** — Transaction patterns, anomaly detection

What would you like me to help you with today?`;
    } else if (lower.includes('statute') || lower.includes('section') || lower.includes('act')) {
      response = `I can help you analyze Indian statutes. Key legal frameworks I cover:

• **PMLA 2002** — Prevention of Money Laundering Act
• **FEMA 1999** — Foreign Exchange Management Act
• **RBI KYC Guidelines** — Master Direction 2016
• **SEBI Regulations** — PIT, LODR, ICDR
• **IBC 2016** — Insolvency and Bankruptcy Code
• **IPC/BNS** — Indian Penal Code / Bharatiya Nyaya Sanhita

Please provide the specific statute or section you'd like analyzed.`;
    } else if (lower.includes('risk') || lower.includes('threat') || lower.includes('danger')) {
      response = `I can assess multiple risk dimensions:

• **Credit Risk** — Default probability, NPA indicators
• **Market Risk** — Price volatility, FX exposure, interest rate risk
• **Liquidity Risk** — Cash flow gaps, funding constraints
• **Operational Risk** — Fraud, cyber threats, process failures
• **Legal Risk** — Litigation exposure, regulatory penalties
• **Compliance Risk** — Regulatory gaps, reporting failures

Provide details about your specific risk concern for a targeted analysis.`;
    } else if (lower.includes('transaction') || lower.includes('payment') || lower.includes('transfer')) {
      response = `I can analyze transactions for:

• **AML Red Flags** — Structuring, round-tripping, shell companies
• **High-Value Alerts** — Transactions above ₹10L threshold
• **Cross-Border Risks** — FEMA compliance, forex violations
• **Pattern Detection** — Unusual frequency, velocity, counterparties
• **Sanctions Screening** — OFAC, FATF watchlist checks

Describe the transaction details and I'll run a comprehensive analysis.`;
    } else {
      response = `I understand you're asking about: "${text}"

I can provide analysis across these domains:

1. **Legal Analysis** — Case law, statutes, precedents
2. **Compliance Review** — Regulatory requirements, gap analysis
3. **Risk Assessment** — Multi-dimensional risk scoring
4. **Document Review** — Contract analysis, clause extraction
5. **Investigation Support** — Pattern analysis, evidence mapping

Could you provide more specific details so I can give you a targeted response? For example, mention relevant statutes, transaction details, or compliance frameworks.`;
    }

    setMessages(prev => prev.map(m =>
      m.id === thinkingId ? { ...m, content: response, status: 'done' } : m,
    ));
  };

  const isWelcome = messages.length === 0;

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-background">
      <ChatHeader isThinking={isThinking} onClear={handleClear} onNew={handleNew} />

      {/* Messages Area */}
      <main className="flex-1 overflow-y-auto px-4">
        <div className="max-w-3xl mx-auto py-6 space-y-1">
          {isWelcome && !isThinking && (
            <div className="text-center py-12 space-y-4">
              <div className="size-16 rounded-2xl bg-gradient-to-br from-amber-600 to-amber-800 mx-auto flex items-center justify-center shadow-lg">
                <span className="text-white text-2xl font-bold">OP</span>
              </div>
              <div>
                <h2 className="text-xl font-semibold">Welcome to GemmaFinOS</h2>
                <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
                  Your AI-powered legal and compliance assistant. Ask me anything about law, compliance, risk, or regulations.
                </p>
              </div>

              {/* Suggested Prompts */}
              <div className="grid gap-2 max-w-lg mx-auto mt-6">
                {SUGGESTED_PROMPTS.slice(0, 4).map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(prompt)}
                    className="text-left px-4 py-2.5 rounded-xl border border-border/50 bg-card hover:bg-muted/50 hover:border-primary/30 transition-all text-xs text-muted-foreground hover:text-foreground"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          <div ref={messagesEndRef} className="h-4" />
        </div>
      </main>

      <ChatInput
        onSend={handleSend}
        onStop={() => setIsThinking(false)}
        isThinking={isThinking}
        disabled={!isLoaded || !user}
      />
    </div>
  );
}
