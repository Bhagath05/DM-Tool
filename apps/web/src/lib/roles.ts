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

/**
 * The internal "owner" role must NEVER surface in the Role Management UI —
 * the creator is shown as Admin, and the separate `admin` system role is
 * what's displayed. Callers filter owner rows out of any role list.
 */
export function isOwnerRole(slug: string): boolean {
  return slug === "owner";
}

/**
 * A member holding `owner` is displayed as an Admin member and is
 * protected (their role assignment can't be edited from this UI).
 */
export function memberIsOwner(roleSlugs: string[]): boolean {
  return roleSlugs.includes("owner");
}

/** Per-permission effect in the tri-state editor. */
export type PermissionEffect = "allow" | "deny" | "inherit";

/**
 * A fallback accent per system-role slug, used only when a role has no
 * explicit `color`. Custom roles always carry their own color.
 */
const ROLE_FALLBACK_COLOR: Record<string, string> = {
  owner: "#6366f1",
  admin: "#6366f1",
  marketing_manager: "#8b5cf6",
  performance_marketer: "#0ea5e9",
  content_creator: "#22c55e",
  designer: "#14b8a6",
  crm_manager: "#f59e0b",
  sales: "#f97316",
  analyst: "#a855f7",
  editor: "#64748b",
  viewer: "#94a3b8",
};

export function roleColor(role: { slug: string; color: string | null }): string {
  return role.color ?? ROLE_FALLBACK_COLOR[role.slug] ?? "#94a3b8";
}

const SLUG_MAX = 64;

/** Derive a valid role slug (`^[a-z][a-z0-9_]{2,63}$`) from a display name. */
export function slugifyRoleName(name: string): string {
  let slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  if (slug && !/^[a-z]/.test(slug)) slug = `r_${slug}`;
  return slug.slice(0, SLUG_MAX);
}

