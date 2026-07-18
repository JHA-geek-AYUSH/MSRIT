/**
 * Track 2 — Gemma Financial Compliance & Risk Triage
 * API client methods for the compliance triage pipeline.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function getAuthHeaders(): Promise<HeadersInit> {
  try {
    if (typeof window !== 'undefined') {
      for (let i = 0; i < 30; i++) {
        const clerk = (window as any).Clerk;
        if (clerk?.session) {
          const token = await clerk.session.getToken();
          if (token) {
            return {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            };
          }
          break;
        }
        await new Promise(r => setTimeout(r, 100));
      }
    }
  } catch {
    // fall through
  }
  return { 'Content-Type': 'application/json' };
}

// ─────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────

export type RiskLevel = 'high' | 'medium' | 'low';

export interface RiskDomain {
  name: string;
  rating: RiskLevel;
  summary: string;
  confidence: number;
}

export interface ComplianceResponse {
  run_id: string;
  overall_rating: RiskLevel;
  domains: RiskDomain[];
  full_report: string;
  recommendations: string[];
  requires_str: boolean;
  requires_edd: boolean;
}

export type TriageMode = 'full' | 'transaction' | 'onboarding' | 'regulatory' | 'financial_risk';

export interface TriageRequest {
  description: string;
  mode?: TriageMode;
  documents?: Record<string, unknown>[];
  context?: Record<string, unknown>;
}

export interface AssessFinding {
  rule_code: string;
  rule_name: string;
  framework: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  max_penalty_inr: number;
  imprisonment_risk: boolean;
  remediation_steps: string[];
  similarity_score: number;
  gap_score: number;
  combined_score: number;
}

export interface AssessResponse {
  assessment_id: string | null;
  risk_tier: 'low' | 'medium' | 'high' | 'critical';
  confidence: number;
  model_fallback: boolean;
  auto_escalated: boolean;
  detected_flags: string[];
  anomaly_summary: string;
  total_penalty_exposure_inr: number;
  imprisonment_risk: boolean;
  findings: AssessFinding[];
  features: Record<string, number>;
}

// ─────────────────────────────────────────────────────────────────────────
// Original triage endpoints
// ─────────────────────────────────────────────────────────────────────────

export async function runComplianceTriage(req: TriageRequest): Promise<ComplianceResponse> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/compliance/triage`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ mode: 'full', ...req }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<ComplianceResponse>;
}

export async function getTriageRun(runId: string) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/compliance/triage/${runId}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export interface TriageHistoryEntry {
  run_id: string;
  status: 'running' | 'completed' | 'failed';
  mode: TriageMode;
  overall_rating: RiskLevel | null;
  requires_str: boolean;
  requires_edd: boolean;
  created_at: string;
  description_preview: string;
}

export async function getTriageHistory(): Promise<{ runs: TriageHistoryEntry[] }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/compliance/triage`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function sendComplianceChat(message: string, context: Record<string, any>) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/compliance/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, session_context: context }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<{ reply: string }>;
}

// ─────────────────────────────────────────────────────────────────────────
// 3-Stage ML Pipeline (POST /v1/compliance/assess)
// ─────────────────────────────────────────────────────────────────────────

export async function runAssessment(req: {
  description?: string;
  features?: Record<string, number>;
  flags?: string[];
  sector?: string;
  business_name?: string;
  persist?: boolean;
}): Promise<AssessResponse> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/compliance/assess`, {
    method: 'POST',
    headers,
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ─────────────────────────────────────────────────────────────────────────
// 7-Tool Agent (POST /v1/agent)
// ─────────────────────────────────────────────────────────────────────────

export interface AgentResponse {
  tool_used: string;
  confidence: number;
  reply: string;
  data: Record<string, any> | null;
}

export async function runAgent(message: string, sessionContext: Record<string, any>): Promise<AgentResponse> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/agent`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, session_context: sessionContext }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ─────────────────────────────────────────────────────────────────────────
// Penalty Simulator
// ─────────────────────────────────────────────────────────────────────────

export interface PenaltyScenario {
  id: string;
  name: string;
  rule_code: string;
  rule_name: string;
  description: string;
  base_fine_inr: number;
  per_day_fine_inr: number;
  max_fine_inr: number;
  imprisonment_months: number;
  aggravating_factors: string[];
}

export async function getPenaltyScenarios() {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/compliance/penalty-scenarios`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<{ total: number; scenarios: PenaltyScenario[] }>;
}

export async function runPenaltySim(payload: {
  scenario_id: string;
  days_since_breach?: number;
  aggravating_factors?: string[];
  repeat_offence?: boolean;
}) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/compliance/penalty-sim`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ─────────────────────────────────────────────────────────────────────────
// Rules Catalogue
// ─────────────────────────────────────────────────────────────────────────

export interface RuleSummary {
  id: number;
  code: string;
  name: string;
  framework: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  max_penalty_inr: number;
  imprisonment_risk: boolean;
}

export async function getRules(params: { framework?: string; severity?: string } = {}) {
  const headers = await getAuthHeaders();
  const filtered = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ) as Record<string, string>;
  const qs = new URLSearchParams(filtered).toString();
  const res = await fetch(`${API_BASE_URL}/v1/compliance/rules${qs ? `?${qs}` : ''}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<{ total: number; rules: RuleSummary[] }>;
}

export async function getRuleDetail(code: string) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/compliance/rules/${code}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ─────────────────────────────────────────────────────────────────────────
// Report Generation
// ─────────────────────────────────────────────────────────────────────────

export async function generateAuditReport(payload: Record<string, any>) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/compliance/report`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ─────────────────────────────────────────────────────────────────────────
// History / Dashboard
// ─────────────────────────────────────────────────────────────────────────

export async function getAssessmentHistory() {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/compliance/history`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function getDashboard() {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/dashboard`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export interface ApprovalRequest {
  id: string;
  action_type: string;
  connector?: string | null;
  risk_level: 'medium' | 'high' | 'critical';
  payload?: Record<string, unknown> | null;
  reason?: string | null;
  status: 'pending' | 'approved' | 'rejected';
  created_at?: string;
}

export async function getPendingApprovals(): Promise<{ approvals: ApprovalRequest[] }> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/approvals?status=pending`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function reviewApproval(id: string, decision: 'approve' | 'reject', comment?: string) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/approvals/${id}/review`, {
    method: 'POST', headers, body: JSON.stringify({ decision, comment }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export interface UserProfile {
  id: string;
  clerk_id: string;
  email: string;
  role: string;
  wallet_address?: string | null;
  created_at: string;
}

export async function getProfile(): Promise<UserProfile> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/users/profile`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function updateProfile(payload: Partial<Pick<UserProfile, 'wallet_address' | 'role'>>): Promise<UserProfile> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/users/profile`, {
    method: 'PUT', headers, body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function askKnowledgeBase(question: string) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/knowledge/ask`, {
    method: 'POST', headers, body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ─────────────────────────────────────────────────────────────────────────
// Connectors / Composio (keep for compatibility)
// ─────────────────────────────────────────────────────────────────────────

export async function getConnectorStatus() {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/connectors/status`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<Record<string, { configured: boolean; connected?: boolean; reason?: string }>>;
}

export async function getComposioToolkits() {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/connectors/composio/toolkits`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<{ configured: boolean; toolkits: string[] }>;
}

export async function connectComposioToolkit(toolkit: string) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/connectors/composio/connect/${toolkit}`, {
    method: 'POST',
    headers,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<{ redirect_url: string | null; connection_id: string | null }>;
}

// ─────────────────────────────────────────────────────────────────────────
// FinOps workflows — invoices, transactions, vendors, unified workflow tracker
// ─────────────────────────────────────────────────────────────────────────

export interface InvoiceExtraction {
  vendor_name: string;
  vendor_gstin: string | null;
  invoice_number: string;
  invoice_date: string;
  amount_net: number;
  amount_gst: number;
  amount_total: number;
  po_number: string | null;
  line_items: Record<string, any>[];
  extraction_confidence: number;
}

export interface InvoiceUploadResponse {
  invoice_id: string;
  status: string;
  extracted_fields: InvoiceExtraction | null;
  validation_findings: Record<string, any>[];
  risk_tier: string | null;
  requires_approval: boolean;
  approval_id: string | null;
  audit_trail: { action: string; actor: string }[];
}

export async function uploadInvoice(file: File, poNumber?: string): Promise<InvoiceUploadResponse> {
  const headers = await getAuthHeaders();
  delete (headers as Record<string, string>)['Content-Type']; // let the browser set multipart boundary
  const form = new FormData();
  form.append('file', file);
  if (poNumber) form.append('po_number', poNumber);
  const res = await fetch(`${API_BASE_URL}/v1/invoices/upload`, { method: 'POST', headers, body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function listInvoices(params: { status?: string; risk_tier?: string } = {}) {
  const headers = await getAuthHeaders();
  // Only include params that have actual values — avoids "?status=undefined" in the URL
  const filtered = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ) as Record<string, string>;
  const qs = new URLSearchParams(filtered).toString();
  const res = await fetch(`${API_BASE_URL}/v1/invoices${qs ? `?${qs}` : ''}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<{ invoices: Record<string, any>[]; total: number }>;
}

export interface TransactionRecord {
  external_id: string;
  supplier: string;
  amount: number;
  transaction_date: string;
  invoice_number?: string | null;
  po_number?: string | null;
  description?: string;
  currency?: string;
  account_code?: string | null;
}

export async function ingestTransactions(transactions: TransactionRecord[], source: string = 'manual') {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/transactions/ingest`, {
    method: 'POST', headers, body: JSON.stringify({ transactions, source }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function listTransactionBatches(params: { risk_tier?: string } = {}) {
  const headers = await getAuthHeaders();
  const filtered = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ) as Record<string, string>;
  const qs = new URLSearchParams(filtered).toString();
  const res = await fetch(`${API_BASE_URL}/v1/transactions/batches${qs ? `?${qs}` : ''}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<{ batches: Record<string, any>[]; total: number }>;
}

export async function onboardVendor(payload: {
  vendor_name: string;
  vendor_gstin?: string;
  vendor_pan?: string;
  sector?: string;
  documents?: File[];
}) {
  const headers = await getAuthHeaders();
  delete (headers as Record<string, string>)['Content-Type'];
  const form = new FormData();
  form.append('vendor_name', payload.vendor_name);
  if (payload.vendor_gstin) form.append('vendor_gstin', payload.vendor_gstin);
  if (payload.vendor_pan) form.append('vendor_pan', payload.vendor_pan);
  if (payload.sector) form.append('sector', payload.sector);
  (payload.documents || []).forEach((f) => form.append('documents', f));
  const res = await fetch(`${API_BASE_URL}/v1/vendors/onboard`, { method: 'POST', headers, body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function listVendorCases(params: { kyc_status?: string } = {}) {
  const headers = await getAuthHeaders();
  const filtered = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ) as Record<string, string>;
  const qs = new URLSearchParams(filtered).toString();
  const res = await fetch(`${API_BASE_URL}/v1/vendors${qs ? `?${qs}` : ''}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<{ cases: Record<string, any>[]; total: number }>;
}

export async function runWorkflow(payload: { workflow_type: string; context?: Record<string, any>; run_llm_agents?: boolean }) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/workflows`, { method: 'POST', headers, body: JSON.stringify(payload) });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function listWorkflows(params: { workflow_type?: string } = {}) {
  const headers = await getAuthHeaders();
  const filtered = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ) as Record<string, string>;
  const qs = new URLSearchParams(filtered).toString();
  const res = await fetch(`${API_BASE_URL}/v1/workflows${qs ? `?${qs}` : ''}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function uploadPolicy(file: File, title?: string, version?: string): Promise<{
  policy_id: string; title: string; version: string;
  compliance_gaps: { rule_code: string; gap_description: string }[];
  gap_analysis_method: 'gemma' | 'keyword_fallback';
}> {
  const headers = await getAuthHeaders();
  delete (headers as Record<string, string>)['Content-Type'];
  const form = new FormData();
  form.append('file', file);
  if (title) form.append('title', title);
  if (version) form.append('version', version);
  const res = await fetch(`${API_BASE_URL}/v1/policies/upload`, { method: 'POST', headers, body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function listPolicies() {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}/v1/policies`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<{ total: number; policies: Record<string, any>[] }>;
}

export async function getAuditTrail(params: {
  entity_type?: string;
  entity_id?: string;
  workflow_id?: string;
  invoice_id?: string;
  limit?: number;
} = {}) {
  const headers = await getAuthHeaders();
  const filtered = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ) as Record<string, string>;
  const qs = new URLSearchParams(filtered).toString();
  const res = await fetch(`${API_BASE_URL}/v1/audit-trail${qs ? `?${qs}` : ''}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<{ total: number; entries: Record<string, any>[] }>;
}
