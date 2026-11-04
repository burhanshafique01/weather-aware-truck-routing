import type { MilesByLevel, RiskLevel } from "./types";

export interface RiskStyle {
  level: RiskLevel;
  key: keyof MilesByLevel;
  label: string;
  color: string;
  text: string;
}

/** Green → yellow → orange → red → deep red; matches the risk table order. */
export const RISK: readonly RiskStyle[] = [
  { level: 0, key: "low", label: "Low", color: "#22a06b", text: "#ffffff" },
  { level: 1, key: "moderate", label: "Moderate", color: "#e2b203", text: "#1f1f1f" },
  { level: 2, key: "high", label: "High", color: "#f18d13", text: "#1f1f1f" },
  { level: 3, key: "severe", label: "Severe", color: "#e34935", text: "#ffffff" },
  { level: 4, key: "no_travel", label: "No Travel", color: "#7d1d6f", text: "#ffffff" },
];

export const riskStyle = (level: number): RiskStyle => RISK[Math.max(0, Math.min(4, level))];

/** Distinct from the risk palette so routes never read as a risk colour. */
export const ROUTE_COLORS: Record<string, string> = {
  A: "#2563eb",
  B: "#7c3aed",
  C: "#0e7490",
};

export const routeColor = (id: string) => ROUTE_COLORS[id] ?? "#475569";
