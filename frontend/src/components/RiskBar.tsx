import { RISK } from "../risk";
import type { MilesByLevel } from "../types";

/** Stacked bar: share of route miles in each risk band. */
export function RiskBar({ miles }: { miles: MilesByLevel }) {
  const total = RISK.reduce((sum, r) => sum + miles[r.key], 0) || 1;
  const title = RISK.filter((r) => miles[r.key] > 0)
    .map((r) => `${r.label}: ${miles[r.key].toFixed(0)} mi`)
    .join(" · ");
  return (
    <div className="risk-bar" title={title} role="img" aria-label={title}>
      {RISK.map((r) =>
        miles[r.key] > 0 ? (
          <span key={r.key} style={{ width: `${(miles[r.key] / total) * 100}%`, background: r.color }} />
        ) : null,
      )}
    </div>
  );
}
