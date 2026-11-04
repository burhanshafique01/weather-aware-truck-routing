import { riskStyle } from "../risk";

export function RiskBadge({ level, compact = false }: { level: number; compact?: boolean }) {
  const s = riskStyle(level);
  return (
    <span className={`risk-badge${compact ? " compact" : ""}`} style={{ background: s.color, color: s.text }}>
      {s.label}
    </span>
  );
}
