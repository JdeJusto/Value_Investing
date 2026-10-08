/**
 * K/M/B/T display helpers ported from `backend/services/ui_format.py`.
 *
 * Rules kept in sync with the Python side:
 * - `None` -> em dash
 * - `0` -> "0"
 * - >= 1e3 abbreviates with K/M/B/T at 2 decimals; a scaled value that
 *   rounds up to 1000 promotes to the next unit (999_999 -> "1.00M")
 * - >= 1e15 falls back to scientific notation (Python `:.1e`)
 * - negatives render in parentheses: ($19.00B)
 */

export const DASH = "—";

const BUCKETS: { factor: number; suffix: string | null }[] = [
  { factor: 1e15, suffix: null },
  { factor: 1e12, suffix: "T" },
  { factor: 1e9, suffix: "B" },
  { factor: 1e6, suffix: "M" },
  { factor: 1e3, suffix: "K" },
];

function abbreviateMagnitude(magnitude: number): string {
  let index = BUCKETS.length;
  for (let i = 0; i < BUCKETS.length; i += 1) {
    if (magnitude >= BUCKETS[i].factor) {
      index = i;
      break;
    }
  }

  if (index >= BUCKETS.length) {
    return magnitude.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  let { factor, suffix } = BUCKETS[index];
  let scaled = magnitude / factor;
  if (suffix !== null && index > 0 && Math.round(scaled * 100) / 100 >= 1000) {
    ({ factor, suffix } = BUCKETS[index - 1]);
    scaled = magnitude / factor;
  }
  return suffix ? `${scaled.toFixed(2)}${suffix}` : magnitude.toExponential(1);
}

function format(value: number | null, withSymbol: boolean): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return DASH;
  }
  const number = Number(value);
  if (number === 0) {
    return "0";
  }
  const text = abbreviateMagnitude(Math.abs(number));
  const signed = withSymbol ? `$${text}` : text;
  return number < 0 ? `(${signed})` : signed;
}

/** `416_161_000_000` -> "$416.16B"; `-19_001_000_000` -> "($19.00B)". */
export function abbreviateCurrency(value: number | null): string {
  return format(value, true);
}

/** Same as `abbreviateCurrency` without the dollar sign. */
export function abbreviateNumber(value: number | null): string {
  return format(value, false);
}

/** Methodology score with two decimals like the desktop; null -> em dash. */
export function formatScore(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return DASH;
  }
  return value.toFixed(2);
}

/** Percentage for display: `-1.411 -> "-141%"` (0 decimals by default). */
export function formatPercent(value: number | null, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return DASH;
  }
  const pct = value * 100;
  const sign = pct < 0 ? "-" : "";
  return `${sign}${Math.abs(pct).toFixed(digits)}%`;
}
