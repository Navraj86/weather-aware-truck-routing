import type { RiskKey } from "../types";

export const RISK_LEVELS: RiskKey[] = ["low", "moderate", "high", "severe", "no_travel"];

export const RISK_LABEL: Record<RiskKey, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  severe: "Severe",
  no_travel: "No Travel",
};

export const RISK_COLOR: Record<RiskKey, string> = {
  low: "#22a06b",
  moderate: "#e6b400",
  high: "#f2780c",
  severe: "#d92d20",
  no_travel: "#6b21a8",
};

/** Text color that stays readable on top of RISK_COLOR. */
export const RISK_INK: Record<RiskKey, string> = {
  low: "#fff",
  moderate: "#2b2100",
  high: "#fff",
  severe: "#fff",
  no_travel: "#fff",
};

export function riskKeyFromScore(score: number): RiskKey {
  return RISK_LEVELS[Math.max(0, Math.min(4, Math.round(score)))];
}
