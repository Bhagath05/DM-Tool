/**
 * Slugify — frontend mirror of the backend SLUG_RX in
 * `apps/api/aicmo/modules/orgs/schemas.py`.
 *
 * Backend rule:
 *   ^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$
 *
 * i.e. 1-40 chars, lowercase alnum + hyphen, can't start/end with hyphen.
 *
 * `slugify` produces a slug that always passes that regex from arbitrary
 * user input. `isValidSlug` is the source-of-truth predicate the wizard
 * uses for inline validation (so the user sees the same verdict the
 * backend will give before submitting).
 */

export const SLUG_MAX_LEN = 40;
const SLUG_RX = /^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$/;

export function isValidSlug(value: string): boolean {
  return SLUG_RX.test(value);
}

/**
 * Convert any string to a valid slug. Best-effort — strips diacritics,
 * collapses non-alnum runs to a single hyphen, trims leading/trailing
 * hyphens, truncates to SLUG_MAX_LEN. Returns "" for input that has no
 * alnum chars (caller should handle that case).
 */
export function slugify(input: string): string {
  const lowered = input.toLowerCase().trim();
  // Strip diacritics via NFD decomposition (é → e + combining accent → e).
  const ascii = lowered.normalize("NFD").replace(/[̀-ͯ]/g, "");
  // Replace any run of non-alnum with a single hyphen.
  const collapsed = ascii.replace(/[^a-z0-9]+/g, "-");
  // Trim leading/trailing hyphens.
  const trimmed = collapsed.replace(/^-+|-+$/g, "");
  // Truncate. If truncation lands on a hyphen, strip it.
  return trimmed.slice(0, SLUG_MAX_LEN).replace(/-+$/, "");
}
