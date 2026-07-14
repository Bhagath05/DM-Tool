"use client";

/**
 * Members tab — who holds this role. Assign / remove operate on the REAL
 * org roster (GET /orgs/{id}/members) via the existing member-role
 * endpoints. Multiple roles per member is fully supported — assigning
 * here just adds this role to whatever they already hold.
 *
 * The internal Owner is never exposed: an owner is surfaced as an Admin
 * member of the Admin role and is protected (no remove affordance).
 */

import { Plus, Search, ShieldCheck, Trash2, UserCircle2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusPill } from "@/components/ui/status-pill";
import { api, type OrgMember, type RbacRole } from "@/lib/api";
import { memberIsOwner } from "@/lib/roles";
import { cn } from "@/lib/utils";

interface Props {
  orgId: string;
  role: RbacRole;
  members: OrgMember[];
  editable: boolean;
  onChanged: () => void;
}

/** Members shown under a role. Admin also surfaces Owner-holders (as Admins). */
function membersForRole(role: RbacRole, members: OrgMember[]): OrgMember[] {
  return members.filter((m) => {
    if (m.role_slugs.includes(role.slug)) return true;
    if (role.slug === "admin" && memberIsOwner(m.role_slugs)) return true;
    return false;
  });
}

export function MembersTab({ orgId, role, members, editable, onChanged }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState("");

  const assigned = useMemo(
    () => membersForRole(role, members),
    [role, members],
  );
  const assignedIds = new Set(assigned.map((m) => m.id));
  const candidates = members.filter((m) => !assignedIds.has(m.id));

  const q = query.trim().toLowerCase();
  const filteredCandidates = q
    ? candidates.filter(
        (m) =>
          m.email.toLowerCase().includes(q) ||
          (m.display_name ?? "").toLowerCase().includes(q),
      )
    : candidates;

  const assign = async (memberId: string) => {
    setBusy(memberId);
    setError(null);
    try {
      await api.orgs.assignMemberRole(orgId, memberId, role.slug);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not assign the role.");
    } finally {
      setBusy(null);
    }
  };

  const remove = async (memberId: string) => {
    setBusy(memberId);
    setError(null);
    try {
      await api.orgs.removeMemberRole(orgId, memberId, role.slug);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove the role.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-4" data-testid="members-tab">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {assigned.length} {assigned.length === 1 ? "member" : "members"} with
          this role
        </p>
        {editable && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setAdding((v) => !v)}
            data-testid="assign-member-toggle"
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            Assign members
          </Button>
        )}
      </div>

      {error && (
        <p className="rounded-md bg-bad-soft px-3 py-2 text-xs text-bad-soft-foreground">
          {error}
        </p>
      )}

      {adding && editable && (
        <div className="rounded-lg border border-border p-3">
          <div className="relative mb-2">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search teammates to add"
              className="pl-8"
              aria-label="Search teammates"
            />
          </div>
          {filteredCandidates.length === 0 ? (
            <p className="py-3 text-center text-xs text-muted-foreground">
              Everyone already has this role.
            </p>
          ) : (
            <ul className="max-h-56 overflow-y-auto">
              {filteredCandidates.map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    disabled={busy === m.id}
                    onClick={() => assign(m.id)}
                    className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left hover:bg-muted disabled:opacity-50"
                  >
                    <Avatar member={m} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm">
                        {m.display_name ?? m.email}
                      </span>
                      {m.display_name && (
                        <span className="block truncate text-xs text-muted-foreground">
                          {m.email}
                        </span>
                      )}
                    </span>
                    <Plus className="h-4 w-4 text-muted-foreground" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {assigned.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No members hold this role yet.
        </p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {assigned.map((m) => {
            const owner = memberIsOwner(m.role_slugs);
            return (
              <li
                key={m.id}
                className="flex items-center gap-3 px-3 py-2.5"
                data-testid="role-member-row"
              >
                <Avatar member={m} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {m.display_name ?? m.email}
                  </p>
                  {m.display_name && (
                    <p className="truncate text-xs text-muted-foreground">
                      {m.email}
                    </p>
                  )}
                </div>
                {owner ? (
                  <StatusPill tone="ai" icon={ShieldCheck}>
                    Protected
                  </StatusPill>
                ) : (
                  <StatusPill tone={m.status === "active" ? "good" : "muted"}>
                    {m.status}
                  </StatusPill>
                )}
                {editable && !owner && (
                  <button
                    type="button"
                    disabled={busy === m.id}
                    onClick={() => remove(m.id)}
                    aria-label={`Remove ${m.display_name ?? m.email} from ${role.name}`}
                    className="rounded-md p-1.5 text-muted-foreground hover:bg-bad-soft hover:text-bad-soft-foreground disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
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
      className={cn(
        "flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground",
      )}
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
