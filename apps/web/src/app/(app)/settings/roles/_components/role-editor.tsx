"use client";

/**
 * Role editor — a modal with four tabs (Display / Permissions / Members /
 * Audit), Discord-style but in the DM Tool design language.
 *
 * System roles are protected: their Display + Permissions are read-only
 * (the backend refuses edits with 409), but you can still assign/remove
 * members and read the audit trail. Custom roles are fully editable and
 * deletable. "Owner" is never rendered — it's filtered upstream.
 */

import { History, Lock, ShieldCheck, Trash2, Users2, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Modal } from "@/components/ui/modal";
import { StatusPill } from "@/components/ui/status-pill";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type OrgMember,
  type RbacPermission,
  type RbacRole,
} from "@/lib/api";
import { ROLE_COLORS } from "./role-form-dialog";
import { roleColor } from "@/lib/roles";
import { cn } from "@/lib/utils";

import { AuditTab } from "./audit-tab";
import { MembersTab } from "./members-tab";
import { PermissionsTab } from "./permissions-tab";

type Tab = "display" | "permissions" | "members" | "audit";

const TABS: { id: Tab; label: string; icon: typeof History }[] = [
  { id: "display", label: "Display", icon: ShieldCheck },
  { id: "permissions", label: "Permissions", icon: Lock },
  { id: "members", label: "Members", icon: Users2 },
  { id: "audit", label: "Audit", icon: History },
];

interface Props {
  orgId: string;
  role: RbacRole;
  permissions: RbacPermission[];
  members: OrgMember[];
  canManage: boolean;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
  onMembersChanged: () => void;
}

export function RoleEditor({
  orgId,
  role,
  permissions,
  members,
  canManage,
  onClose,
  onSaved,
  onDeleted,
  onMembersChanged,
}: Props) {
  const editable = canManage && !role.is_system;

  const [tab, setTab] = useState<Tab>("display");

  // Draft (Display + Permissions).
  const [name, setName] = useState(role.name);
  const [description, setDescription] = useState(role.description ?? "");
  const [color, setColor] = useState(roleColor(role));
  const [priority, setPriority] = useState(role.priority);
  const [allow, setAllow] = useState<Set<string>>(
    () => new Set(role.permission_slugs),
  );
  const [deny, setDeny] = useState<Set<string>>(
    () => new Set(role.deny_slugs),
  );

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const dirty = useMemo(() => {
    const setsEqual = (a: Set<string>, b: string[]) =>
      a.size === b.length && b.every((s) => a.has(s));
    return (
      name !== role.name ||
      description !== (role.description ?? "") ||
      color !== roleColor(role) ||
      priority !== role.priority ||
      !setsEqual(allow, role.permission_slugs) ||
      !setsEqual(deny, role.deny_slugs)
    );
  }, [name, description, color, priority, allow, deny, role]);

  const setEffect = (slug: string, effect: "allow" | "deny" | "inherit") => {
    setAllow((prev) => {
      const next = new Set(prev);
      if (effect === "allow") next.add(slug);
      else next.delete(slug);
      return next;
    });
    setDeny((prev) => {
      const next = new Set(prev);
      if (effect === "deny") next.add(slug);
      else next.delete(slug);
      return next;
    });
  };

  const reset = () => {
    setName(role.name);
    setDescription(role.description ?? "");
    setColor(roleColor(role));
    setPriority(role.priority);
    setAllow(new Set(role.permission_slugs));
    setDeny(new Set(role.deny_slugs));
    setError(null);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.rbac.updateRole(orgId, role.id, {
        name,
        description: description || null,
        color,
        priority,
        permission_slugs: [...allow],
        deny_slugs: [...deny],
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't save your changes.");
    } finally {
      setSaving(false);
    }
  };

  const doDelete = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.rbac.deleteRole(orgId, role.id);
      onDeleted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't delete this role.");
      setSaving(false);
    }
  };

  const showFooter = editable && (tab === "display" || tab === "permissions");

  return (
    <Modal
      open
      onOpenChange={(o) => !o && onClose()}
      className="w-full max-w-3xl"
      data-testid="role-editor"
    >
      <div className="flex max-h-[80vh] flex-col">
        {/* Header */}
        <div className="flex items-start gap-3 border-b border-border pb-4">
          <span
            className="mt-1 h-4 w-4 shrink-0 rounded-full"
            style={{ backgroundColor: color }}
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-lg font-semibold">{role.name}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              {role.is_system ? (
                <StatusPill tone="ai" icon={Lock}>
                  Protected system role
                </StatusPill>
              ) : (
                <StatusPill tone="neutral">Custom role</StatusPill>
              )}
              <StatusPill tone="muted">
                {role.member_count}{" "}
                {role.member_count === 1 ? "member" : "members"}
              </StatusPill>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tabs */}
        <div
          role="tablist"
          aria-label="Role editor"
          className="flex gap-1 overflow-x-auto border-b border-border"
        >
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={active}
                onClick={() => setTab(t.id)}
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors",
                  active
                    ? "border-foreground text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
                data-testid={`role-tab-${t.id}`}
              >
                <Icon className="h-4 w-4" />
                {t.label}
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div className="min-h-0 flex-1 overflow-y-auto py-4">
          {tab === "display" && (
            <DisplayTab
              editable={editable}
              isSystem={role.is_system}
              name={name}
              setName={setName}
              description={description}
              setDescription={setDescription}
              color={color}
              setColor={setColor}
              priority={priority}
              setPriority={setPriority}
              createdAt={role.created_at}
              updatedAt={role.updated_at}
              canDelete={editable}
              onRequestDelete={() => setConfirmDelete(true)}
            />
          )}
          {tab === "permissions" && (
            <PermissionsTab
              permissions={permissions}
              allow={allow}
              deny={deny}
              editable={editable}
              onSet={setEffect}
            />
          )}
          {tab === "members" && (
            <MembersTab
              orgId={orgId}
              role={role}
              members={members}
              editable={canManage}
              onChanged={onMembersChanged}
            />
          )}
          {tab === "audit" && <AuditTab orgId={orgId} roleId={role.id} />}
        </div>

        {error && (
          <p className="rounded-md bg-bad-soft px-3 py-2 text-xs text-bad-soft-foreground">
            {error}
          </p>
        )}

        {/* Footer */}
        {showFooter && (
          <div className="flex items-center justify-between gap-3 border-t border-border pt-4">
            <span
              className={cn(
                "text-xs",
                dirty ? "text-watch-soft-foreground" : "text-muted-foreground",
              )}
              data-testid="unsaved-indicator"
            >
              {dirty ? "You have unsaved changes" : "All changes saved"}
            </span>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                onClick={reset}
                disabled={!dirty || saving}
              >
                Reset
              </Button>
              <Button onClick={save} disabled={!dirty || saving}>
                {saving ? "Saving…" : "Save changes"}
              </Button>
            </div>
          </div>
        )}

        {!editable && role.is_system && tab !== "audit" && (
          <p className="border-t border-border pt-3 text-xs text-muted-foreground">
            <Lock className="mr-1 inline h-3 w-3" />
            System roles are protected. You can assign members and view the
            audit trail, but the name and permissions are fixed.
          </p>
        )}
      </div>

      {/* Delete confirmation — fixed above the modal, not clipped by it. */}
      {confirmDelete && (
        <div
          className="fixed inset-0 z-[210] flex items-center justify-center bg-black/50 p-6 backdrop-blur-sm"
          data-testid="delete-confirm"
        >
          <div className="w-full max-w-sm rounded-lg border border-border bg-background p-5 shadow-lg">
            <div className="mb-2 flex items-center gap-2">
              <Trash2 className="h-4 w-4 text-bad" />
              <h3 className="text-sm font-semibold">Delete “{role.name}”?</h3>
            </div>
            <p className="mb-4 text-sm text-muted-foreground">
              This permanently removes the role and unassigns it from every
              member. This can't be undone.
            </p>
            <div className="flex justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirmDelete(false)}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={doDelete}
                disabled={saving}
              >
                {saving ? "Deleting…" : "Delete role"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}

function DisplayTab({
  editable,
  isSystem,
  name,
  setName,
  description,
  setDescription,
  color,
  setColor,
  priority,
  setPriority,
  createdAt,
  updatedAt,
  canDelete,
  onRequestDelete,
}: {
  editable: boolean;
  isSystem: boolean;
  name: string;
  setName: (v: string) => void;
  description: string;
  setDescription: (v: string) => void;
  color: string;
  setColor: (v: string) => void;
  priority: number;
  setPriority: (v: number) => void;
  createdAt: string;
  updatedAt: string;
  canDelete: boolean;
  onRequestDelete: () => void;
}) {
  return (
    <div className="flex flex-col gap-5" data-testid="display-tab">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="edit-name">Role name</Label>
        <Input
          id="edit-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={!editable}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="edit-desc">Description</Label>
        <Textarea
          id="edit-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={!editable}
          rows={2}
          placeholder="What is this role for?"
        />
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label>Color</Label>
          <div className="flex flex-wrap gap-2">
            {ROLE_COLORS.map((c) => (
              <button
                key={c}
                type="button"
                aria-label={`Color ${c}`}
                aria-pressed={color === c}
                disabled={!editable}
                onClick={() => setColor(c)}
                className={cn(
                  "h-6 w-6 rounded-full ring-offset-2 ring-offset-background transition disabled:cursor-default",
                  color === c && "ring-2 ring-foreground",
                )}
                style={{ backgroundColor: c }}
              />
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-priority">Priority</Label>
          <Input
            id="edit-priority"
            type="number"
            min={0}
            max={1000}
            value={priority}
            onChange={(e) => setPriority(Number(e.target.value) || 0)}
            disabled={!editable}
            className="max-w-28"
          />
          <p className="text-xs text-muted-foreground">
            Higher priority sits above lower ones in the hierarchy.
          </p>
        </div>
      </div>

      <dl className="flex flex-wrap gap-x-8 gap-y-1 border-t border-border pt-4 text-xs text-muted-foreground">
        <div>
          <dt className="inline font-medium">Created</dt>{" "}
          <dd className="inline">{new Date(createdAt).toLocaleDateString()}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Updated</dt>{" "}
          <dd className="inline">{new Date(updatedAt).toLocaleDateString()}</dd>
        </div>
        {isSystem && (
          <div>
            <dt className="inline font-medium">Type</dt>{" "}
            <dd className="inline">Protected system role</dd>
          </div>
        )}
      </dl>

      {canDelete && (
        <div className="mt-2 flex items-center justify-between rounded-lg border border-bad-border bg-bad-soft/40 px-4 py-3">
          <div>
            <p className="text-sm font-medium">Delete this role</p>
            <p className="text-xs text-muted-foreground">
              Removes it from every member. Can't be undone.
            </p>
          </div>
          <Button
            variant="destructive"
            size="sm"
            onClick={onRequestDelete}
            data-testid="delete-role-button"
          >
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            Delete
          </Button>
        </div>
      )}
    </div>
  );
}
