import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Browser-compatible UUID generator (no crypto.randomUUID dependency)
export function generateId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for non-secure contexts
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 11) + Math.random().toString(36).slice(2, 7);
}
