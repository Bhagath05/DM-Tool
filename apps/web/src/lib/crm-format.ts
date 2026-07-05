/**
 * Phase 6.5 consolidation — one set of CRM display formatters, shared across the
 * board, directory, tasks, email, dashboard, and insight components (previously
 * copy-pasted into each). Keeps money/percent/label formatting identical
 * everywhere so the CRM reads as one product.
 */

export function money(value: number, currency = "USD"): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${currency} ${Math.round(value).toLocaleString()}`;
  }
}

export const pct = (v: number): string => `${Math.round(v * 100)}%`;

export function humanize(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}
