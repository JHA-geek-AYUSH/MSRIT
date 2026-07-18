// ── Database Operations ──────────────────────────────────────
// Lightweight CRUD for memory, tasks, and user operations.
// Uses the API routes (not direct Supabase calls) for portability.

import type { ComplianceTriageResult, MemoryEntry, MemoryType, Task, TaskStep } from '@/types/chat';
import { apiClient } from '@/lib/api';

// ── Task Operations ──────────────────────────────────────────

export async function createTask(input: string, title?: string): Promise<Task> {
  const res = await fetch('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input, title: title || input.slice(0, 80) }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Failed to create task' }));
    throw new Error(err.error || 'Failed to create task');
  }
  return res.json();
}

export async function getTask(taskId: string): Promise<Task | null> {
  try {
    const res = await fetch(`/api/tasks/${taskId}`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getTasks(status?: string): Promise<Task[]> {
  try {
    const params = status ? `?status=${status}` : '';
    const res = await fetch(`/api/tasks${params}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.tasks || data || [];
  } catch {
    return [];
  }
}

// ── Memory Operations ────────────────────────────────────────

export async function getMemories(type?: MemoryType): Promise<MemoryEntry[]> {
  try {
    const params = type ? `?type=${type}` : '';
    const res = await fetch(`/api/memory${params}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.memories || data || [];
  } catch {
    return [];
  }
}

export async function createMemory(data: {
  content: string;
  type: MemoryType;
  importance?: number;
  source?: string;
}): Promise<MemoryEntry | null> {
  try {
    const res = await fetch('/api/memory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) return null;
    const result = await res.json();
    return result.memory || result;
  } catch {
    return null;
  }
}

export async function deleteMemory(id: string): Promise<boolean> {
  try {
    const res = await fetch(`/api/memory?id=${id}`, { method: 'DELETE' });
    return res.ok;
  } catch {
    return false;
  }
}

export async function searchMemories(query: string): Promise<MemoryEntry[]> {
  try {
    const res = await fetch(`/api/memory/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.memories || data || [];
  } catch {
    return [];
  }
}

// ── Compliance Operations ────────────────────────────────────

export async function runComplianceTriage(data: {
  description: string;
  mode?: 'full' | 'transaction' | 'onboarding' | 'regulatory' | 'financial_risk';
}): Promise<{
  run_id: string;
  overall_rating: ComplianceTriageResult['overall_rating'];
  domains: ComplianceTriageResult['domains'];
  full_report: string;
  recommendations: string[];
  requires_str: boolean;
  requires_edd: boolean;
}> {
  const res = await apiClient.complianceTriage(data);
  if (res.error) throw new Error(res.error);
  return res.data!;
}

// ── Analytics Operations ─────────────────────────────────────

export async function getStats(): Promise<{
  tasksCompleted: number;
  memoriesStored: number;
  activeTime: string;
}> {
  try {
    const [tasks, memories] = await Promise.all([
      getTasks(),
      getMemories(),
    ]);
    const completedCount = tasks.filter(t => t.status === 'success').length;
    const hours = Math.round(tasks.reduce((acc, t) => {
      if (t.updated_at && t.created_at) {
        return acc + (new Date(t.updated_at).getTime() - new Date(t.created_at).getTime());
      }
      return acc;
    }, 0) / 3600000);

    return {
      tasksCompleted: completedCount,
      memoriesStored: memories.length,
      activeTime: `${hours}h`,
    };
  } catch {
    return { tasksCompleted: 0, memoriesStored: 0, activeTime: '0h' };
  }
}
