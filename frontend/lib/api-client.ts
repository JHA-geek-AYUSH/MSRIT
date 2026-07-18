// ── API Client ──────────────────────────────────────────────
// Re-exports the main apiClient and also provides direct fetch helpers

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
                Authorization: `Bearer ${token}`,
              };
            }
            break;
          }
          await new Promise(r => setTimeout(r, 100));
        }
      }
      return { 'Content-Type': 'application/json' };
    } catch {
      return { 'Content-Type': 'application/json' };
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
        const errorMsg = data.detail || data.message || `HTTP ${response.status}`;
        return { error: typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg), status: response.status };
      }
      return { data, status: response.status };
    } catch (error) {
      return { error: error instanceof Error ? error.message : 'Network error', status: 500 };
    }
  }

  async complianceTriage(data: {
    description: string;
    mode?: string;
    documents?: Record<string, unknown>[];
    context?: Record<string, unknown>;
  }) {
    return this.request<any>('/v1/compliance/triage', {
      method: 'POST',
      body: JSON.stringify({ mode: 'full', ...data }),
    });
  }

  async health() { return this.request<any>('/'); }
  async getCaseTypes() { return this.request<string[]>('/v1/case-types'); }
  async getJurisdictions() { return this.request<string[]>('/v1/jurisdictions'); }
  async getAnalytics() { return this.request<any>('/v1/analytics/dashboard'); }
}

export const apiClient = new ApiClient();
export default apiClient;
