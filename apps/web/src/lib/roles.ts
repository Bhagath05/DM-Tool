/**
 * Phase 6.6 — role display.
 *
 * "Owner" is an INTERNAL-only concept: the workspace creator is stored as the
 * `owner` system role purely so ownership can't be accidentally deleted or
 * transferred. It has identical permissions to `admin`. The UI must NEVER show
 * "Owner" — the creator, like any full administrator, is shown as "Admin".
 * Every place that renders a role slug goes through this helper.
 */
export function displayRoleName(slug: string): string {
  if (slug === "owner") return "Admin";
  return slug.replace(/[_-]+/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}
