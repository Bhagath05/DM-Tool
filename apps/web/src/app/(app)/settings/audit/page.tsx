"use client";

/**
 * Settings · Audit log — org-wide activity trail (Phase 6.6 Slice 4).
 *
 * Reads the EXISTING audit trail (GET /orgs/{id}/audit), gated on
 * `organization.manage`. Filter by search, action, category, and date
 * range; export the current view to CSV. Every row is a real recorded
 * event — nothing is fabricated.
 */

import {
  Download,
  History,
  Search,
  ShieldAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonLines } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { api, type AuditEvent } from "@/lib/api";
import {
  actionCategory,
  actionLabel,
  actorLabel,
  auditToCsv,
  type AuditCategory,
} from "@/lib/audit-format";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

const CATEGORIES: AuditCategory[] = [
  "Organization",
  "Members",
  "Roles",
  "Invitations",
  "Security",
  "Other",
];

export default function AuditSettingsPage() {
  const tenant = useTenant();
  const orgId = tenant.activeOrg?.id ?? null;
  const canView = tenant.can("organization.manage");

  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [actions, setActions] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Server-side filters.
  const [search, setSearch] = useState("");
  const [action, setAction] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  // Client-side filter.
  const [category, setCategory] = useState<AuditCategory | "">("");

  const load = useCallback(async () => {
    if (!orgId) return;
    setError(null);
    try {
      const res = await api.audit.list(orgId, {
        search: search.trim() || undefined,
        action: action ? [action] : undefined,
        since: since ? new Date(since).toISOString() : undefined,
        until: until ? new Date(`${until}T23:59:59`).toISOString() : undefined,
        limit: 500,
      });
      setEvents(res.items);
      setActions(res.actions);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "We couldn't load the audit log.",
      );
      setEvents([]);
    }
  }, [orgId, search, action, since, until]);

  useEffect(() => {
    if (!orgId || !canView) return;
    const t = setTimeout(() => void load(), 250); // light debounce on typing
    return () => clearTimeout(t);
  }, [orgId, canView, load]);

  const visible = useMemo(() => {
    const list = events ?? [];
    return category
      ? list.filter((e) => actionCategory(e.action) === category)
      : list;
  }, [events, category]);

  const exportCsv = () => {
    const csv = auditToCsv(visible);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!canView) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Audit log is admin-only"
        description="You need the Manage organization permission to view the workspace audit trail."
      />
    );
  }

  return (
    <div className="flex flex-col gap-6" data-testid="settings-audit">
      <SectionHeading
        eyebrow="Settings · Audit log"
        heading="Activity & audit trail"
        description="Every administrative change in this workspace — who did what, and when. Filter, search, and export for compliance."
        size="lg"
        action={
          <Button
            size="sm"
            variant="outline"
            onClick={exportCsv}
            disabled={visible.length === 0}
            data-testid="audit-export"
          >
            <Download className="mr-1.5 h-3.5 w-3.5" />
            Export CSV
          </Button>
        }
      />

      {/* Filters */}
      <div className="flex flex-col gap-3 rounded-lg border border-border p-3 sm:flex-row sm:flex-wrap sm:items-end">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">
            Search
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Action, actor, entity"
              className="pl-8"
              aria-label="Search audit log"
              data-testid="audit-search"
            />
          </div>
        </div>
        <Field label="Action">
          <NativeSelect
            value={action}
            onChange={setAction}
            data-testid="audit-action-filter"
          >
            <option value="">All actions</option>
            {actions.map((a) => (
              <option key={a} value={a}>
                {actionLabel(a)}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Category">
          <NativeSelect
            value={category}
            onChange={(v) => setCategory(v as AuditCategory | "")}
          >
            <option value="">All</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="From">
          <Input
            type="date"
            value={since}
            onChange={(e) => setSince(e.target.value)}
            className="w-auto"
          />
        </Field>
        <Field label="To">
          <Input
            type="date"
            value={until}
            onChange={(e) => setUntil(e.target.value)}
            className="w-auto"
          />
        </Field>
      </div>

      {error && (
        <p className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad-soft-foreground">
          {error}
        </p>
      )}

      {events === null ? (
        <SkeletonLines lines={8} />
      ) : visible.length === 0 ? (
        <EmptyState
          icon={History}
          title="No activity found"
          description="No audit events match these filters. Try widening the date range or clearing filters."
        />
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {visible.length} {visible.length === 1 ? "event" : "events"}
          </p>
          <ol className="flex flex-col divide-y divide-border rounded-lg border border-border">
            {visible.map((e) => (
              <li
                key={e.id}
                className="flex items-start gap-3 px-3 py-2.5"
                data-testid="audit-row"
              >
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <History className="h-3.5 w-3.5" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm">
                    <span className="font-medium">
                      {actionLabel(e.action)}
                    </span>
                    <span className="text-muted-foreground">
                      {" "}
                      · {actorLabel(e)}
                    </span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    <time dateTime={e.occurred_at} title={new Date(e.occurred_at).toLocaleString()}>
                      {new Date(e.occurred_at).toLocaleString()}
                    </time>
                    {e.target_type && (
                      <span> · {e.target_type}</span>
                    )}
                  </p>
                </div>
                <StatusPill tone={toneFor(actionCategory(e.action))} size="sm">
                  {actionCategory(e.action)}
                </StatusPill>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

function toneFor(category: AuditCategory) {
  switch (category) {
    case "Security":
      return "bad" as const;
    case "Roles":
      return "ai" as const;
    case "Invitations":
      return "watch" as const;
    case "Members":
      return "good" as const;
    default:
      return "muted" as const;
  }
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

function NativeSelect({
  value,
  onChange,
  children,
  ...rest
}: {
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
  "data-testid"?: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "h-9 rounded-md border border-input bg-background px-2 text-sm shadow-sm",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
      )}
      {...rest}
    >
      {children}
    </select>
  );
}
