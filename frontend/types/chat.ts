// ──────────────────────────────────────────────────────────────
// Chat, Task & Memory Types — AgentOS Integration
// ──────────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'agent' | 'system';
export type MessageStatus = 'sending' | 'thinking' | 'streaming' | 'done' | 'error';

export interface ToolExecutionCard {
  tool: string;
  description: string;
  status: 'running' | 'done' | 'error';
  result?: unknown;
  formattedResult?: string;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  timestamp: string;
  taskId?: string;
  toolExecutions?: ToolExecutionCard[];
  planSteps?: Array<{ tool: string; description: string; status: string }>;
  authInfo?: {
    type: 'REQUIRES_AUTH';
    toolkit: string;
    authUrl: string;
    message: string;
  };
  complianceResult?: ComplianceTriageResult;
}

export interface ComplianceTriageResult {
  run_id: string;
  overall_rating: 'high' | 'medium' | 'low';
  domains: Array<{
    name: string;
    rating: 'high' | 'medium' | 'low';
    summary: string;
    confidence: number;
  }>;
  full_report: string;
  recommendations: string[];
  requires_str: boolean;
  requires_edd: boolean;
}

// ── Task Types ───────────────────────────────────────────────

export interface TaskPlan {
  goal: string;
  answer?: string | null;
  steps: PlanStep[];
  reasoning?: string;
}

export interface PlanStep {
  id: string;
  order: number;
  tool: string;
  input: Record<string, unknown>;
  description: string;
  depends_on: string[];
  status?: 'pending' | 'running' | 'success' | 'failed';
}

export interface Task {
  id: string;
  user_id: string;
  title: string;
  description?: string;
  status: 'pending' | 'running' | 'success' | 'failed';
  input: string;
  plan?: TaskPlan;
  result?: unknown;
  error?: string;
  created_at: string;
  updated_at: string;
  steps?: TaskStep[];
}

export interface TaskStep {
  id: string;
  task_id: string;
  step_order: number;
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_output?: unknown;
  status: 'pending' | 'running' | 'success' | 'failed';
  error?: string;
  created_at: string;
}

// ── Memory Types ─────────────────────────────────────────────

export interface MemoryEntry {
  id: string;
  user_id: string;
  type: MemoryType;
  content: string;
  source?: string;
  metadata: Record<string, unknown>;
  importance: number;
  created_at: string;
  updated_at: string;
}

export type MemoryType = 'fact' | 'preference' | 'context' | 'interaction' | 'task_summary' | 'key_output';

// ── Tool Types ───────────────────────────────────────────────

export interface ToolDefinition {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
}

export interface ToolResult {
  success: boolean;
  data?: unknown;
  error?: string;
  executionId?: string;
  toolName?: string;
  durationMs?: number;
  authRequired?: boolean;
  toolkit?: string;
  authUrl?: string;
}

// ── Agent Types ──────────────────────────────────────────────

export interface Agent {
  id: string;
  name: string;
  status: 'idle' | 'planning' | 'executing' | 'paused' | 'completed' | 'failed';
  config: {
    name: string;
    model: string;
    temperature: number;
    maxTokens: number;
  };
  currentPlan?: TaskPlan;
  thoughts: AgentThought[];
  memories: string[];
  metrics: {
    totalExecutions: number;
    successfulExecutions: number;
    selfCorrections: number;
  };
}

export interface AgentThought {
  id: string;
  thought: string;
  reasoning: string;
  decision: string;
  confidence: number;
  timestamp: string;
}

export interface BackgroundTask {
  id: string;
  name: string;
  status: 'running' | 'completed' | 'failed' | 'paused';
  progress: number;
  progressMessage?: string;
}

// ── Composio / Integration Types ─────────────────────────────

export interface Toolkit {
  slug: string;
  name: string;
  description: string;
  logo?: string;
  category?: string;
  authSchemes: string[];
  connection?: {
    is_active: boolean;
    connected_account?: unknown;
  } | null;
}

export interface UserStats {
  tasksCompleted: number;
  memoriesStored: number;
  activeTime: string;
}
