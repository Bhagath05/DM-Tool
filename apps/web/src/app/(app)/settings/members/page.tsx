"use client";

/**
 * Settings · Members — enterprise member management (Phase 6.6 Slice 4).
 *
 * Real roster from GET /orgs/{id}/members (avatar, name, email, status,
 * roles, last active, joined). Search / sort / status filter, per-member
 * role management + deactivate/reactivate/remove, and bulk actions — all
 * through the existing member endpoints (which enforce the last-Admin and
 * privilege-escalation guards server-side). Invitations live in the panel
 * below. The internal Owner is shown as an Admin and is protected.
 */

import {
  ChevronDown,
  Crown,
  Power,
  Search,
  Trash2,
  UserCircle2,
  UserCog,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonLines } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { api, type OrgMember, type RbacRole } from "@/lib/api";
import { displayRoleName, isOwnerRole, memberIsOwner } from "@/lib/roles";
import { cn } from "@/lib/utils";

import { InvitationsPanel } from "./_components/invitations-panel";

export const dynamic = "force-dynamic";

type SortKey = "name" | "joined" | "active";

export default function MembersSettingsPage() {
  const tenant = useTenant();
  const orgId = tenant.activeOrg?.id ?? null;
  const canManage = tenant.can("team.manage");
  const iAmOwner = tenant.roleSlugs.includes("owner");
  const myUserId = tenant.user?.id ?? null;

  const [members, setMembers] = useState<OrgMember[] | null>(null);
  const [roles, setRoles] = useState<RbacRole[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "suspended">("all");
  const [sort, setSort] = useState<SortKey>("name");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [bulkRole, setBulkRole] = useState("");

  const load = useCallback(async () => {
    if (!orgId) return;
    setError(null);
    try {
      setMembers((await api.orgs.members(orgId, true)).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "We couldn't load your members.");
      setMembers([]);
    }
  }, [orgId]);

  useEffect(() => {
    if (!orgId) return;
    void load();
    api.rbac
      .listRoles(orgId)
      .then((r) => setRoles(r.items.filter((x) => !isOwnerRole(x.slug))))
      .catch(() => setRoles([]));
  }, [orgId, load]);

  const view = useMemo(() => {
    let list = members ?? [];
    const q = query.trim().toLowerCase();
    if (q)
      list = list.filter(
        (m) =>
          (m.display_name ?? "").toLowerCase().includes(q) ||
          m.email.toLowerCase().includes(q),
      );
    if (statusFilter !== "all")
      list = list.filter((m) => m.status === statusFilter);
    const name = (m: OrgMember) => (m.display_name ?? m.email).toLowerCase();
    return [...list].sort((a, b) => {
      if (sort === "name") return name(a).localeCompare(name(b));
      if (sort === "joined")
        return +new Date(b.joined_at) - +new Date(a.joined_at);
      return (
        +new Date(b.last_active_at ?? 0) - +new Date(a.last_active_at ?? 0)
      );
    });
  }, [members, query, statusFilter, sort]);

  const toggleSel = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const runBulk = async (
    fn: (orgId: string, memberId: string) => Promise<unknown>,
  ) => {
    if (!orgId) return;
    setBusy("bulk");
    setError(null);
    const ids = [...selected];
    for (const id of ids) {
      try {
        await fn(orgId, id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "One or more actions failed.");
      }
    }
    setSelected(new Set());
    setBusy(null);
    await load();
  };

  const act = async (fn: () => Promise<unknown>, key: string) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That action didn't work.");
    } finally {
      setBusy(null);
    }
  };

  if (!orgId) return <SkeletonLines lines={6} />;

  return (
    <div className="flex flex-col gap-8" data-testid="settings-members">
      <SectionHeading
        eyebrow="Settings · Members"
        heading="Members"
        description="Everyone in this workspace, their roles, and their access. Assign roles, deactivate access, or remove members — changes are audited."
        size="lg"
      />

      {/* Controls */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name or email"
            className="pl-8"
            aria-label="Search members"
            data-testid="member-search"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          aria-label="Filter by status"
          className="h-9 rounded-md border border-input bg-background px-2 text-sm shadow-sm"
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Deactivated</option>
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          aria-label="Sort members"
          className="h-9 rounded-md border border-input bg-background px-2 text-sm shadow-sm"
        >
          <option value="name">Sort: Name</option>
          <option value="joined">Sort: Recently joined</option>
          <option value="active">Sort: Recently active</option>
        </select>
      </div>

      {/* Bulk action bar */}
      {canManage && selected.size > 0 && (
        <div
          className="flex flex-wrap items-center gap-2 rounded-lg border border-ai-border bg-ai-soft px-3 py-2"
          data-testid="bulk-bar"
        >
          <span className="text-sm font-medium text-ai-soft-foreground">
            {selected.size} selected
          </span>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <select
              value={bulkRole}
              onChange={(e) => setBulkRole(e.target.value)}
              aria-label="Role to assign"
              className="h-8 rounded-md border border-input bg-background px-2 text-xs shadow-sm"
            >
              <option value="">Assign role…</option>
              {roles.map((r) => (
                <option key={r.id} value={r.slug}>
                  {r.name}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              variant="outline"
              disabled={busy === "bulk" || !bulkRole}
              onClick={() =>
                runBulk((oid, mid) =>
                  api.orgs.assignMemberRole(oid, mid, bulkRole),
                )
              }
            >
              Assign
            </Button>
            <span aria-hidden className="h-5 w-px bg-ai-border" />
            <Button
              size="sm"
              variant="outline"
              disabled={busy === "bulk"}
              onClick={() => runBulk(api.orgs.deactivateMember)}
            >
              Deactivate
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy === "bulk"}
              onClick={() => runBulk(api.orgs.reactivateMember)}
            >
              Reactivate
            </Button>
            <Button
              size="sm"
              variant="destructive"
              disabled={busy === "bulk"}
              onClick={() => runBulk(api.orgs.removeMember)}
            >
              Remove
            </Button>
          </div>
        </div>
      )}

      {error && (
        <p className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad-soft-foreground">
          {error}
        </p>
      )}

      {members === null ? (
        <SkeletonLines lines={6} />
      ) : view.length === 0 ? (
        <EmptyState
          icon={UserCircle2}
          title="No members found"
          description="No members match your search or filters."
        />
      ) : (
        <ul className="flex flex-col gap-2" data-testid="member-list">
          {view.map((m) => {
            const owner = memberIsOwner(m.role_slugs);
            const isSelf = myUserId != null && m.user_id === myUserId;
            const isOpen = expanded === m.id;
            return (
              <li
                key={m.id}
                className="rounded-lg border border-border bg-background"
                data-testid="member-row"
              >
                <div className="flex items-center gap-3 px-3 py-2.5">
                  {canManage && !owner && (
                    <Checkbox
                      checked={selected.has(m.id)}
                      onCheckedChange={() => toggleSel(m.id)}
                      aria-label={`Select ${m.display_name ?? m.email}`}
                    />
                  )}
                  <Avatar member={m} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">
                        {m.display_name ?? m.email}
                      </span>
                      {isSelf && (
                        <span className="text-xs text-muted-foreground">
                          (you)
                        </span>
                      )}
                    </div>
                    <p className="truncate text-xs text-muted-foreground">
                      {m.email}
                    </p>
                  </div>

                  {/* Roles */}
                  <div className="hidden max-w-[40%] flex-wrap justify-end gap-1 md:flex">
                    {(owner ? ["admin"] : m.role_slugs).slice(0, 3).map((s) => (
                      <StatusPill key={s} tone="neutral" size="sm">
                        {displayRoleName(s)}
                      </StatusPill>
                    ))}
                  </div>

                  {/* Last active */}
                  <span className="hidden w-24 shrink-0 text-right text-xs text-muted-foreground lg:block">
                    {m.last_active_at
                      ? `active ${relative(m.last_active_at)}`
                      : "—"}
                  </span>

                  {/* Status */}
                  <StatusPill
                    tone={m.status === "active" ? "good" : "muted"}
                    size="sm"
                  >
                    {m.status === "suspended" ? "deactivated" : m.status}
                  </StatusPill>

                  {canManage && (
                    <button
                      type="button"
                      onClick={() => setExpanded(isOpen ? null : m.id)}
                      aria-label={`Manage ${m.display_name ?? m.email}`}
                      aria-expanded={isOpen}
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                    >
                      <ChevronDown
                        className={cn(
                          "h-4 w-4 transition-transform",
                          isOpen && "rotate-180",
                        )}
                      />
                    </button>
                  )}
                </div>

                {/* Expanded management */}
                {isOpen && canManage && (
                  <div className="border-t border-border px-3 py-3">
                    {owner ? (
                      <p className="text-xs text-muted-foreground">
                        This member owns the workspace and is protected. Their
                        roles and access can't be changed here.
                      </p>
                    ) : (
                      <MemberManage
                        orgId={orgId}
                        member={m}
                        roles={roles}
                        isSelf={isSelf}
                        iAmOwner={iAmOwner}
                        busy={busy}
                        onAct={act}
                      />
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <div className="border-t border-border pt-8">
        <InvitationsPanel canManage={canManage} />
      </div>
    </div>
  );
}

function MemberManage({
  orgId,
  member,
  roles,
  isSelf,
  iAmOwner,
  busy,
  onAct,
}: {
  orgId: string;
  member: OrgMember;
  roles: RbacRole[];
  isSelf: boolean;
  iAmOwner: boolean;
  busy: string | null;
  onAct: (fn: () => Promise<unknown>, key: string) => Promise<void>;
}) {
  const [confirmTransfer, setConfirmTransfer] = useState(false);
  const has = (slug: string) => member.role_slugs.includes(slug);
  const toggleRole = (slug: string) =>
    onAct(
      () =>
        has(slug)
          ? api.orgs.removeMemberRole(orgId, member.id, slug)
          : api.orgs.assignMemberRole(orgId, member.id, slug),
      `${member.id}:${slug}`,
    );

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
          <UserCog className="h-3.5 w-3.5" /> Roles
        </p>
        <div className="flex flex-wrap gap-1.5">
          {roles.map((r) => {
            const on = has(r.slug);
            return (
              <button
                key={r.id}
                type="button"
                disabled={busy === `${member.id}:${r.slug}`}
                onClick={() => toggleRole(r.slug)}
                aria-pressed={on}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50",
                  on
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-muted",
                )}
              >
                {r.name}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {member.status === "active" ? (
          <Button
            size="sm"
            variant="outline"
            disabled={isSelf || busy === `deact:${member.id}`}
            onClick={() =>
              onAct(
                () => api.orgs.deactivateMember(orgId, member.id),
                `deact:${member.id}`,
              )
            }
          >
            <Power className="mr-1.5 h-3.5 w-3.5" />
            Deactivate
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            disabled={busy === `react:${member.id}`}
            onClick={() =>
              onAct(
                () => api.orgs.reactivateMember(orgId, member.id),
                `react:${member.id}`,
              )
            }
          >
            <Power className="mr-1.5 h-3.5 w-3.5" />
            Reactivate
          </Button>
        )}
        <Button
          size="sm"
          variant="destructive"
          disabled={isSelf || busy === `rm:${member.id}`}
          onClick={() =>
            onAct(
              () => api.orgs.removeMember(orgId, member.id),
              `rm:${member.id}`,
            )
          }
        >
          <Trash2 className="mr-1.5 h-3.5 w-3.5" />
          Remove
        </Button>
      </div>

      {/* Ownership transfer — only the current owner sees this. */}
      {iAmOwner && !isSelf && member.status === "active" && (
        <div className="rounded-lg border border-watch-border bg-watch-soft/40 px-3 py-2.5">
          {confirmTransfer ? (
            <div className="flex flex-wrap items-center gap-2">
              <p className="flex-1 text-xs text-foreground">
                Make {member.display_name ?? member.email} the owner? You'll
                stay on as an Admin. This can only be undone by the new owner.
              </p>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setConfirmTransfer(false)}
                disabled={busy === `owner:${member.id}`}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() =>
                  onAct(async () => {
                    await api.orgs.transferOwnership(orgId, member.id);
                    setConfirmTransfer(false);
                  }, `owner:${member.id}`)
                }
                disabled={busy === `owner:${member.id}`}
              >
                <Crown className="mr-1.5 h-3.5 w-3.5" />
                Confirm transfer
              </Button>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium">Transfer ownership</p>
                <p className="text-xs text-muted-foreground">
                  Hand this workspace to another member.
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirmTransfer(true)}
                data-testid={`transfer-owner-${member.id}`}
              >
                <Crown className="mr-1.5 h-3.5 w-3.5" />
                Make owner
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Avatar({ member }: { member: OrgMember }) {
  const initials = (member.display_name ?? member.email)
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase())
    .join("");
  return (
    <span
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground"
      aria-hidden
    >
      {member.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={member.avatar_url}
          alt=""
          className="h-full w-full rounded-full object-cover"
        />
      ) : initials ? (
        initials
      ) : (
        <UserCircle2 className="h-5 w-5" />
      )}
    </span>
  );
}

function relative(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const days = Math.round((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "1d ago";
  if (days < 30) return `${days}d ago`;
  return d.toLocaleDateString();
}
