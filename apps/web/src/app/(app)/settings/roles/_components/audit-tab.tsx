"use client";

/**
 * Audit tab — reads the EXISTING audit trail (GET /orgs/{id}/roles/{id}/
 * audit), scoped to this role. Shows role.created / updated / deleted and
 * member.role_assigned / removed events. No new logging is invented here;
 * every row is a real recorded event.
 */

import {
  History,
  Pencil,
  Search,
  Shuffle,
  Trash2,
  UserMinus,
  UserPlus,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Input } from "@/components/ui/input";
import { SkeletonLines } from "@/components/ui/skeleton";
import { api, type RoleAuditEvent } from "@/lib/api";

interface Props {
  orgId: string;
  roleId: string;
}

const ACTION_ICON: Record<string, typeof History> = {
  "role.created": History,
  "role.updated": Pencil,
  "role.deleted": Trash2,
  "role.reordered": Shuffle,
  "member.role_assigned": UserPlus,
  "member.role_removed": UserMinus,
};

export function AuditTab({ orgId, roleId }: Props) {
  const [events, setEvents] = useState<RoleAuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.rbac.roleAudit(orgId, roleId);
      setEvents(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the audit log.");
    }
  }, [orgId, roleId]);

  useEffect(() => {
    void load();
  }, [load]);

  const q = query.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!events) return [];
    if (!q) return events;
    return events.filter(
      (e) =>
        (e.summary ?? "").toLowerCase().includes(q) ||
        e.action.toLowerCase().includes(q) ||
        (e.actor_name ?? "").toLowerCase().includes(q) ||
        (e.actor_email ?? "").toLowerCase().includes(q),
    );
  }, [events, q]);

  return (
    <div className="flex flex-col gap-4" data-testid="audit-tab">
      <div className="relative sm:max-w-xs">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search the audit log"
          className="pl-8"
          aria-label="Search audit log"
        />
      </div>

      {error && (
        <p className="rounded-md bg-bad-soft px-3 py-2 text-xs text-bad-soft-foreground">
          {error}
        </p>
      )}

      {events === null ? (
        <SkeletonLines lines={4} />
      ) : filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {events.length === 0
            ? "No activity recorded for this role yet."
            : `No entries match “${query}”.`}
        </p>
      ) : (
        <ol className="flex flex-col gap-1">
          {filtered.map((e) => {
            const Icon = ACTION_ICON[e.action] ?? History;
            const actor = e.actor_name ?? e.actor_email ?? "System";
            return (
              <li
                key={e.id}
                className="flex items-start gap-3 rounded-lg px-2 py-2 hover:bg-muted/50"
                data-testid="audit-row"
              >
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <Icon className="h-3.5 w-3.5" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm">
                    <span className="font-medium">{e.summary ?? e.action}</span>
                    <span className="text-muted-foreground"> · {actor}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    <time dateTime={e.occurred_at} title={formatAbsolute(e.occurred_at)}>
                      {formatRelative(e.occurred_at)}
                    </time>
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function formatAbsolute(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function formatRelative(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diff = Date.now() - d.getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return d.toLocaleDateString();
}
