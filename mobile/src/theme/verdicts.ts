import type { Theme } from "./index";

/** Verdict colors shared by chips and badges (desktop palette). */
const VERDICT_COLORS: Record<string, string> = {
  BUY: "#3bb273", // accent green
  WATCH: "#f4a261", // warning amber
  HOLD: "#00acc1", // cyan
  AVOID: "#e63946", // danger red
};

/** Color for a verdict; N/A and INSUFFICIENT_DATA stay dim (muted). */
export function verdictColor(verdict: string, theme: Theme): string {
  return VERDICT_COLORS[verdict] ?? theme.muted;
}

/** DCF verdict colors (UNDER green, FAIR amber, OVER red). */
const DCF_VERDICT_COLORS: Record<string, string> = {
  UNDERVALUED: "#3bb273",
  FAIR: "#f4a261",
  OVERVALUED: "#e63946",
};

/** Color for a DCF verdict; INSUFFICIENT_DATA stays dim (muted). */
export function dcfVerdictColor(verdict: string, theme: Theme): string {
  return DCF_VERDICT_COLORS[verdict] ?? theme.muted;
}
