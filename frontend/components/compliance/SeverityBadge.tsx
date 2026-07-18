import { getRiskTheme } from "./RiskTheme";

export function SeverityBadge({ severity, size = "sm" }: { severity?: string | null; size?: "sm" | "md" }) {
  const theme = getRiskTheme(severity);
  const sizeClasses = size === "md" ? "text-xs px-3 py-1" : "text-[10px] px-2.5 py-0.5";
  return (
    <span className={`${sizeClasses} uppercase font-medium font-body border rounded-full ${theme.badge}`}>
      {severity || "unknown"}
    </span>
  );
}
