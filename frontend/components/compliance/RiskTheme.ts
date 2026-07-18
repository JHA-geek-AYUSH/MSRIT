export const RISK_THEME: Record<string, { bg: string; text: string; border: string; badge: string }> = {
  critical: { bg: "bg-error-500/10", text: "text-error-500", border: "border-error-500/40", badge: "bg-error-500 text-cream-50 border-error-500" },
  high: { bg: "bg-error-500/5", text: "text-error-500", border: "border-error-500/30", badge: "bg-error-500/10 text-error-500 border-error-500/40" },
  medium: { bg: "bg-gold-500/10", text: "text-gold-500", border: "border-gold-500/30", badge: "bg-gold-500/15 text-gold-500 border-gold-500/40" },
  low: { bg: "bg-olive-400/10", text: "text-olive-400", border: "border-olive-400/30", badge: "bg-olive-400/15 text-olive-400 border-olive-400/40" },
  unknown: { bg: "bg-brown-500/5", text: "text-brown-500", border: "border-brown-500/20", badge: "bg-brown-500/10 text-brown-500 border-brown-500/30" },
};

export function getRiskTheme(tier?: string | null) {
  return RISK_THEME[tier?.toLowerCase() || "unknown"] || RISK_THEME.unknown;
}
