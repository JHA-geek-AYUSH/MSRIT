// ── API Client — Full client for GemmaFinOS FastAPI backend ───────

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface ApiResponse<T> {
  data?: T;
  error?: string;
  status: number;
}

class ApiClient {
  private baseURL: string;

  constructor(baseURL: string = API_BASE_URL) {
    this.baseURL = baseURL;
  }

  private async getAuthHeaders(): Promise<HeadersInit> {
    try {
      if (typeof window !== 'undefined') {
        for (let i = 0; i < 30; i++) {
          const clerk = (window as any).Clerk;
          if (clerk?.session) {
            const token = await clerk.session.getToken();
            if (token) {
              return {
                'Content-Type': 'application/json',
                'ngrok-skip-browser-warning': 'true',
                Authorization: `Bearer ${token}`,
              };
            }
            break;
          }
          await new Promise(r => setTimeout(r, 100));
        }
      }
      return {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
      };
    } catch {
      return { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' };
    }
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
    try {
      const headers = await this.getAuthHeaders();
      const response = await fetch(`${this.baseURL}${endpoint}`, {
        ...options,
        headers: { ...headers, ...options.headers },
      });
      const data = await response.json();
      if (!response.ok) {
        let errorMsg = `HTTP ${response.status}`;
        if (typeof data.detail === 'string') errorMsg = data.detail;
        else if (Array.isArray(data.detail)) errorMsg = data.detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ');
        else if (data.detail) errorMsg = JSON.stringify(data.detail);
        else if (data.message) errorMsg = typeof data.message === 'string' ? data.message : JSON.stringify(data.message);
        return { error: errorMsg, status: response.status };
      }
      return { data, status: response.status };
    } catch (error) {
      return { error: error instanceof Error ? error.message : 'Network error', status: 500 };
    }
  }

  async health() { return this.request<any>('/'); }
  async getCaseTypes() { return this.request<string[]>('/v1/case-types'); }
  async getJurisdictions() { return this.request<string[]>('/v1/jurisdictions'); }

  // Matters
  async createMatter(data: { title: string }) {
    const r = await this.request<{ id: string; title: string }>('/v1/matters', {
      method: 'POST', body: JSON.stringify({ title: data.title, language: 'en' }),
    });
    if (r.data && r.data.id) return { ...r, data: { id: r.data.id, title: r.data.title } }; return r;
  }
  async getMatters() { return this.request<any>('/v1/matters'); }
  async getMatter(id: string) { return this.request<any>(`/v1/matters/${id}`); }

  // Documents
  async uploadDocument(matterId: string, file: File, court?: string, caseNumber?: string) {
    try {
      const headers = await this.getAuthHeaders();
      const formData = new FormData();
      formData.append('file', file);
      if (court) formData.append('court', court);
      if (caseNumber) formData.append('case_number', caseNumber);
      const response = await fetch(`${this.baseURL}/v1/matters/${matterId}/documents`, {
        method: 'POST',
        headers: { 'ngrok-skip-browser-warning': 'true', ...((headers as any).Authorization && { Authorization: (headers as any).Authorization }) },
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) {
        const errorMsg = data.detail || data.message || `HTTP ${response.status}`;
        return { error: typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg), status: response.status };
      }
      return { data, status: response.status };
    } catch (error) {
      return { error: error instanceof Error ? error.message : 'Upload failed', status: 500 };
    }
  }
  async getDocuments(matterId: string) { return this.request<any>(`/v1/matters/${matterId}/documents`); }

  // Chat
  async sendChatMessage(data: { matter_id: string; message: string; facts?: string; case_type?: string; jurisdiction_region?: string; mode?: string }) {
    return this.request<any>('/v1/chat', {
      method: 'POST',
      body: JSON.stringify({ matterId: data.matter_id, message: data.message, mode: data.mode || 'general', filters: { facts: data.facts, case_type: data.case_type, jurisdiction_region: data.jurisdiction_region } }),
    });
  }
  async sendChatFollowup(data: { matter_id: string; run_id: string; message: string }) {
    const formData = new FormData();
    formData.append('matter_id', data.matter_id); formData.append('run_id', data.run_id); formData.append('message', data.message);
    return this.request<any>('/v1/chat-followup', { method: 'POST', body: formData as any });
  }

  // Runs
  async getRun(runId: string) { return this.request<any>(`/v1/runs/${runId}`); }
  async exportRun(runId: string, format = 'docx') { return this.request<any>(`/v1/runs/${runId}/export`, { method: 'POST', body: JSON.stringify({ format }) }); }

  // Conversation
  async getConversationHistory(matterId: string) { return this.request<any>(`/v1/conversation/${matterId}`); }
  async clearConversationHistory(matterId: string) { return this.request<any>(`/v1/conversation/${matterId}`, { method: 'DELETE' }); }
  async exportConversationHistory(matterId: string) { return this.request<any>(`/v1/conversation/${matterId}/export`); }

  // Notarization
  async notarizeRun(runId: string, usePrivateSubnet = true) {
    return this.request<any>(usePrivateSubnet ? `/v1/subnet/runs/${runId}/notarize` : `/v1/runs/${runId}/notarize`, { method: 'POST', body: JSON.stringify({ include_audit_commit: true }) });
  }
  async getNotarization(runId: string, usePrivateSubnet = true) {
    return this.request<any>(usePrivateSubnet ? `/v1/subnet/notary/${runId}` : `/v1/notary/${runId}`);
  }

  // User
  async getUser() { return this.request<any>('/v1/users/profile'); }
  async updateUser(data: { wallet_address?: string }) { return this.request<any>('/v1/users/profile', { method: 'PUT', body: JSON.stringify(data) }); }

  // Analytics
  async getAnalytics() {
    const raw = await this.request<any>('/v1/analytics/dashboard');
    if (raw.error || !raw.data) return raw;
    const d = raw.data;
    return {
      status: raw.status,
      data: { total_queries: d.recent_activity?.queries_last_30_days ?? 0, total_documents: d.recent_activity?.documents_uploaded ?? 0, avg_confidence: d.quick_stats?.success_rate ?? 0, credits_used: d.recent_activity?.credits_spent ?? 0, recent_activity: [] },
    };
  }

  // Subscriptions
  async getSubscription() { return this.request<any>('/v1/subscriptions'); }

  // ── Compliance Triage (Track 2 — Gemma) ────────────────────
  async complianceTriage(data: {
    description: string;
    mode?: 'full' | 'transaction' | 'onboarding' | 'regulatory' | 'financial_risk';
    documents?: Record<string, unknown>[];
    context?: Record<string, unknown>;
  }) {
    return this.request<{
      run_id: string;
      overall_rating: 'high' | 'medium' | 'low';
      domains: Array<{ name: string; rating: 'high' | 'medium' | 'low'; summary: string; confidence: number }>;
      full_report: string;
      recommendations: string[];
      requires_str: boolean;
      requires_edd: boolean;
    }>('/v1/compliance/triage', {
      method: 'POST',
      body: JSON.stringify({ mode: 'full', ...data }),
    });
  }

  // Search
  async search(query: string, filters?: { type?: string; date_from?: string; date_to?: string; limit?: number; offset?: number }) {
    const params = new URLSearchParams();
    params.append('q', query);
    if (filters) {
      if (filters.type) params.append('type', filters.type);
      if (filters.date_from) params.append('date_from', filters.date_from);
      if (filters.date_to) params.append('date_to', filters.date_to);
      if (filters.limit) params.append('limit', filters.limit.toString());
      if (filters.offset) params.append('offset', filters.offset.toString());
    }
    return this.request<any>(`/v1/search?${params.toString()}`);
  }
}

export const apiClient = new ApiClient();
export default apiClient;
