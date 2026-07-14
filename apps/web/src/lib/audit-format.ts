/**
 * Phase 6.6 Slice 4 — audit-event presentation.
 *
 * Maps the real `action` slugs recorded by the backend audit writer to a
 * friendly label + a coarse category (for filtering). Unknown actions
 * degrade gracefully to a title-cased label so newly-recorded event types
 * appear automatically. No event data is invented here.
 */

import type { AuditEvent } from "@/lib/api";

export type AuditCategory =
  | "Organization"
  | "Members"
  | "Roles"
  | "Invitations"
  | "Security"
  | "Other";

interface ActionMeta {
  label: string;
  category: AuditCategory;
}

const ACTIONS: Record<string, ActionMeta> = {
  "organization.created": { label: "Organization created", category: "Organization" },
  "organization.updated": { label: "Organization updated", category: "Organization" },
  "organization.deleted": { label: "Organization deleted", category: "Organization" },
  "organization.reset": { label: "Workspace reset", category: "Organization" },
  "brand.created": { label: "Brand created", category: "Organization" },
  "brand.updated": { label: "Brand updated", category: "Organization" },
  "brand.archived": { label: "Brand archived", category: "Organization" },
  "member.invited": { label: "User invited", category: "Invitations" },
  "member.invite_revoked": { label: "Invitation revoked", category: "Invitations" },
  "member.invite_resent": { label: "Invitation resent", category: "Invitations" },
  "member.invite_accepted": { label: "Invitation accepted", category: "Invitations" },
  "member.removed": { label: "Member removed", category: "Members" },
  "member.deactivated": { label: "Member deactivated", category: "Members" },
  "member.reactivated": { label: "Member reactivated", category: "Members" },
  "member.role_assigned": { label: "Role assigned", category: "Members" },
  "member.role_removed": { label: "Role removed", category: "Members" },
  "role.created": { label: "Role created", category: "Roles" },
  "role.updated": { label: "Role updated", category: "Roles" },
  "role.deleted": { label: "Role deleted", category: "Roles" },
  "role.reordered": { label: "Roles reordered", category: "Roles" },
  "login": { label: "Signed in", category: "Security" },
  "session.revoked": { label: "Session revoked", category: "Security" },
};

function titleCase(slug: string): string {
  return slug
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

export function actionLabel(action: string): string {
  return ACTIONS[action]?.label ?? titleCase(action);
}

export function actionCategory(action: string): AuditCategory {
  return ACTIONS[action]?.category ?? "Other";
}

export function actorLabel(e: AuditEvent): string {
  return e.actor_name ?? e.actor_email ?? "System";
}

function csvCell(value: string): string {
  // Escape per RFC 4180: wrap in quotes if it contains a comma, quote, or newline.
  if (/[",\n]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
  return value;
}

/** Build a CSV export of the given audit events. Header + one row each. */
export function auditToCsv(events: AuditEvent[]): string {
  const header = ["When", "Action", "Category", "Actor", "Actor email", "Target"];
  const rows = events.map((e) =>
    [
      new Date(e.occurred_at).toISOString(),
      actionLabel(e.action),
      actionCategory(e.action),
      actorLabel(e),
      e.actor_email ?? "",
      e.target_type ?? "",
    ]
      .map(csvCell)
      .join(","),
  );
  return [header.join(","), ...rows].join("\n");
}
