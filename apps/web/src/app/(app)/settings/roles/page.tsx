"use client";

/**
 * Settings · Roles — enterprise Role Management.
 *
 * Lists every role in the workspace (system + custom), searchable, with a
 * live member count, permission summary, hierarchy priority and color.
 * Clicking a role opens the full editor (Display / Permissions / Members /
 * Audit). Custom roles can be created, duplicated, reordered (drag or the
 * ↑/↓ buttons) and deleted; system roles are protected.
 *
 * Everything is real data scoped to the active org — no mock roles, no
 * fabricated members, no placeholder permissions. The internal Owner role
 * is never shown; the creator appears as an Admin.
 */

import {
  ChevronDown,
  ChevronUp,
  Copy,
  GripVertical,
  Lock,
  PlusCircle,
  Search,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonLines } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import {
  api,
  type OrgMember,
  type RbacPermission,
  type RbacRole,
} from "@/lib/api";
import { isOwnerRole, roleColor } from "@/lib/roles";
import { cn } from "@/lib/utils";

import { RoleEditor } from "./_components/role-editor";
import { RoleFormDialog } from "./_components/role-form-dialog";

export const dynamic = "force-dynamic";

export default function RolesSettingsPage() {
  const tenant = useTenant();
  const orgId = tenant.activeOrg?.id ?? null;
  const canManage = tenant.can("team.manage");

  const [roles, setRoles] = useState<RbacRole[] | null>(null);
  const [permissions, setPermissions] = useState<RbacPermission[]>([]);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<
    { mode: "create" | "duplicate"; source: RbacRole | null } | null
  >(null);
  const [dragId, setDragId] = useState<string | null>(null);

  const loadRoles = useCallback(async () => {
    if (!orgId) return;
    try {
      const res = await api.rbac.listRoles(orgId);
      setRoles(res.items.filter((r) => !isOwnerRole(r.slug)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't load your roles.");
    }
  }, [orgId]);

  const loadMembers = useCallback(async () => {
    if (!orgId) return;
    try {
      setMembers((await api.orgs.members(orgId)).items);
    } catch {
      /* members are secondary — the roles list still works without them */
    }
  }, [orgId]);

  useEffect(() => {
    if (!orgId) return;
    void loadRoles();
    void loadMembers();
    api.rbac
      .permissions()
      .then((r) => setPermissions(r.items))
      .catch(() => setPermissions([]));
  }, [orgId, loadRoles, loadMembers]);

  const q = query.trim().toLowerCase();
  const visible = useMemo(() => {
    const list = roles ?? [];
    if (!q) return list;
    return list.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        r.slug.toLowerCase().includes(q) ||
        (r.description ?? "").toLowerCase().includes(q),
    );
  }, [roles, q]);

  const editing = roles?.find((r) => r.id === editingId) ?? null;
  const dragEnabled = canManage && !q;

  /** Persist a single custom role's new priority (midpoint of its new neighbors). */
  const reorder = useCallback(
    async (draggedId: string, targetId: string) => {
      if (!orgId || !roles || draggedId === targetId) return;
      const dragged = roles.find((r) => r.id === draggedId);
      if (!dragged || dragged.is_system) return;

      const order = [...roles].sort((a, b) => b.priority - a.priority);
      const from = order.findIndex((r) => r.id === draggedId);
      const to = order.findIndex((r) => r.id === targetId);
      if (from < 0 || to < 0) return;
      order.splice(to, 0, order.splice(from, 1)[0]);

      const i = order.findIndex((r) => r.id === draggedId);
      const above = order[i - 1];
      const below = order[i + 1];
      let priority: number;
      if (above && below) {
        priority = Math.round((above.priority + below.priority) / 2);
        if (priority >= above.priority) priority = above.priority - 1;
        if (priority <= below.priority) priority = below.priority + 1;
      } else if (!above && below) {
        priority = below.priority + 10;
      } else if (above && !below) {
        priority = Math.max(above.priority - 10, 0);
      } else {
        return;
      }
      priority = Math.min(Math.max(priority, 0), 1000);

      // Optimistic.
      setRoles((prev) =>
        prev
          ? prev.map((r) => (r.id === draggedId ? { ...r, priority } : r))
          : prev,
      );
      try {
        const res = await api.rbac.reorderRoles(orgId, [
          { role_id: draggedId, priority },
        ]);
        setRoles(res.items.filter((r) => !isOwnerRole(r.slug)));
      } catch {
        void loadRoles();
      }
    },
    [orgId, roles, loadRoles],
  );

  const moveBy = (roleId: string, dir: -1 | 1) => {
    if (!roles) return;
    const order = [...roles].sort((a, b) => b.priority - a.priority);
    const idx = order.findIndex((r) => r.id === roleId);
    const target = order[idx + dir];
    if (target) void reorder(roleId, target.id);
  };

  if (!orgId) {
    return (
      <div className="py-12">
        <SkeletonLines lines={4} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8" data-testid="settings-roles">
      <SectionHeading
        eyebrow="Settings · Roles"
        heading="Roles & permissions"
        description="Define what each role can do, who holds it, and how roles rank. Search, create, duplicate, reorder — system roles are protected."
        size="lg"
        action={
          canManage ? (
            <Button
              size="sm"
              onClick={() => setForm({ mode: "create", source: null })}
              data-testid="create-role-button"
            >
              <PlusCircle className="mr-2 h-3.5 w-3.5" />
              Create role
            </Button>
          ) : undefined
        }
      />

      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search roles"
          className="pl-8"
          aria-label="Search roles"
          data-testid="role-search"
        />
      </div>

      {error && (
        <p className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad-soft-foreground">
          {error}
        </p>
      )}

      {roles === null ? (
        <SkeletonLines lines={6} />
      ) : visible.length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title={q ? "No roles match your search" : "No roles yet"}
          description={
            q
              ? "Try a different name or clear the search."
              : "Create your first custom role to get started."
          }
        />
      ) : (
        <ul className="flex flex-col gap-2" data-testid="role-list">
          {visible.map((role) => (
            <li
              key={role.id}
              draggable={dragEnabled && !role.is_system}
              onDragStart={() => setDragId(role.id)}
              onDragEnd={() => setDragId(null)}
              onDragOver={(e) => {
                if (dragEnabled && dragId && dragId !== role.id)
                  e.preventDefault();
              }}
              onDrop={() => {
                if (dragId) void reorder(dragId, role.id);
                setDragId(null);
              }}
              className={cn(
                "group flex items-center gap-2 rounded-lg border border-border bg-background px-2.5 py-2.5 transition-colors sm:gap-3 sm:px-3",
                dragId === role.id && "opacity-50",
                "hover:border-foreground/20",
              )}
              data-testid="role-row"
            >
              {/* Drag handle / reorder */}
              {dragEnabled && !role.is_system ? (
                <div className="flex flex-col items-center">
                  <button
                    type="button"
                    aria-label={`Move ${role.name} up`}
                    onClick={() => moveBy(role.id, -1)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <ChevronUp className="h-3.5 w-3.5" />
                  </button>
                  <GripVertical
                    className="h-4 w-4 cursor-grab text-muted-foreground"
                    aria-hidden
                  />
                  <button
                    type="button"
                    aria-label={`Move ${role.name} down`}
                    onClick={() => moveBy(role.id, 1)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <ChevronDown className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : (
                <span className="flex w-4 justify-center" aria-hidden>
                  {role.is_system ? (
                    <Lock className="h-3.5 w-3.5 text-muted-foreground/60" />
                  ) : null}
                </span>
              )}

              {/* Color */}
              <span
                className="h-8 w-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: roleColor(role) }}
                aria-hidden
              />

              {/* Main — opens the editor */}
              <button
                type="button"
                onClick={() => setEditingId(role.id)}
                className="flex min-w-0 flex-1 items-center gap-3 text-left"
                data-testid={`open-role-${role.slug}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold">
                      {role.name}
                    </span>
                    {role.is_system && (
                      <StatusPill tone="ai" size="sm" icon={Lock}>
                        System
                      </StatusPill>
                    )}
                  </div>
                  {role.description && (
                    <p className="truncate text-xs text-muted-foreground">
                      {role.description}
                    </p>
                  )}
                </div>

                <div className="hidden shrink-0 items-center gap-4 text-xs text-muted-foreground sm:flex">
                  <span>{permissionSummary(role, permissions.length)}</span>
                  <span>
                    {role.member_count}{" "}
                    {role.member_count === 1 ? "member" : "members"}
                  </span>
                </div>
              </button>

              {/* Duplicate */}
              {canManage && (
                <button
                  type="button"
                  aria-label={`Duplicate ${role.name}`}
                  onClick={() => setForm({ mode: "duplicate", source: role })}
                  className="rounded-md p-1.5 text-muted-foreground opacity-0 transition hover:bg-muted hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
                  data-testid={`duplicate-role-${role.slug}`}
                >
                  <Copy className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {editing && (
        <RoleEditor
          orgId={orgId}
          role={editing}
          permissions={permissions}
          members={members}
          canManage={canManage}
          onClose={() => setEditingId(null)}
          onSaved={() => {
            void loadRoles();
          }}
          onDeleted={() => {
            setEditingId(null);
            void loadRoles();
          }}
          onMembersChanged={() => {
            void loadMembers();
            void loadRoles();
          }}
        />
      )}

      {form && (
        <RoleFormDialog
          open
          orgId={orgId}
          mode={form.mode}
          source={form.source}
          onClose={() => setForm(null)}
          onCreated={(role) => {
            setForm(null);
            void loadRoles();
            setEditingId(role.id);
          }}
        />
      )}
    </div>
  );
}

function permissionSummary(role: RbacRole, total: number): string {
  const n = role.permission_slugs.length;
  if (total > 0 && n >= total) return "All permissions";
  if (n === 0) return "No permissions";
  return `${n} ${n === 1 ? "permission" : "permissions"}`;
}
