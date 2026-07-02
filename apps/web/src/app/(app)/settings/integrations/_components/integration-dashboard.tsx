"use client";

/**
 * Phase 6.1 — Integration operations dashboard.
 *
 * Enterprise observability over the EXISTING integration platform. Reuses the
 * real APIs only (catalog / events / analytics) — no new services, no fabricated
 * providers. Powers: Connected Apps health, Integration Analytics, and one
 * activity feed that becomes the Activity Log / Sync History / Error Center via
 * tabs + filters, with client-side search, sort, pagination, and CSV export.
 */

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Download,
  RefreshCw,
  Search,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { Surface } from "@/components/ui/surface";
import {
  api,
  type IntegrationAnalytics,
  type IntegrationCatalogEntry,
  type IntegrationConnectionState,
  type IntegrationEvent,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 15;

type Tab = "all" | "sync" | "errors";

const STATE_TONE: Record<IntegrationConnectionState, PillTone> = {
  ACTIVE: "good",
  ERROR: "bad",
  EXPIRED: "watch",
  SUSPENDED: "watch",
  PENDING_AUTH: "ai",
  DISCONNECTED: "muted",
};

function statusTone(status: string): PillTone {
  if (status === "success") return "good";
  if (status === "failure") return "bad";
  return "neutral";
}

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function pct(v: number | null): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function toCsv(rows: IntegrationEvent[]): string {
  const head = [
    "occurred_at",
    "provider",
    "event_type",
    "status",
    "duration_ms",
    "message",
  ];
  const esc = (s: unknown) => `"${String(s ?? "").replace(/"/g, '""')}"`;
  const body = rows.map((r) =>
    [
      r.occurred_at,
      r.provider_slug,
      r.event_type,
      r.status,
      r.duration_ms ?? "",
      r.message ?? "",
    ]
      .map(esc)
      .join(","),
  );
  return [head.join(","), ...body].join("\n");
}

function download(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function Kpi({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad" | "default";
}) {
  return (
    <Surface padding="compact" className="flex flex-col gap-1">
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span
        className={cn(
          "text-2xl font-semibold tabular-nums",
          tone === "good" && "text-good",
          tone === "bad" && "text-bad",
        )}
      >
        {value}
      </span>
    </Surface>
  );
}

export function IntegrationDashboard() {
  const [catalog, setCatalog] = useState<IntegrationCatalogEntry[]>([]);
  const [analytics, setAnalytics] = useState<IntegrationAnalytics | null>(null);
  const [events, setEvents] = useState<IntegrationEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [tab, setTab] = useState<Tab>("all");
  const [providerFilter, setProviderFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [sortDesc, setSortDesc] = useState(true);
  const [page, setPage] = useState(0);

  const load = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [cat, an, ev] = await Promise.all([
        api.integrations.catalog(),
        api.integrations.analytics(30),
        api.integrations.events({
          event_type: tab === "sync" ? "sync_completed" : undefined,
          status: tab === "errors" ? "failure" : undefined,
          provider: providerFilter || undefined,
          limit: 500,
        }),
      ]);
      setCatalog(cat);
      setAnalytics(an);
      setEvents(ev);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load integrations.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [tab, providerFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setPage(0);
  }, [tab, providerFilter, search]);

  const connected = useMemo(
    () => catalog.filter((c) => c.connection),
    [catalog],
  );

  const providerOptions = useMemo(() => {
    const s = new Set(catalog.map((c) => c.provider.slug));
    return Array.from(s).sort();
  }, [catalog]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = events;
    if (q) {
      rows = rows.filter(
        (e) =>
          (e.message ?? "").toLowerCase().includes(q) ||
          e.provider_slug.toLowerCase().includes(q) ||
          e.event_type.toLowerCase().includes(q),
      );
    }
    return [...rows].sort((a, b) => {
      const cmp = a.occurred_at.localeCompare(b.occurred_at);
      return sortDesc ? -cmp : cmp;
    });
  }, [events, search, sortDesc]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-8" data-testid="integration-dashboard">
      {/* Analytics KPIs */}
      <section className="space-y-3">
        <SectionHeading
          eyebrow="Last 30 days"
          heading="Integration analytics"
          size="md"
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => void load()}
              disabled={refreshing}
              data-testid="integrations-refresh"
            >
              <RefreshCw
                className={cn("h-4 w-4", refreshing && "animate-spin")}
              />
              Refresh
            </Button>
          }
        />
        {error && (
          <Surface state="bad" padding="compact" className="text-sm text-bad">
            {error}
          </Surface>
        )}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Kpi
            label="Connected"
            value={String(analytics?.connections_total ?? 0)}
          />
          <Kpi
            label="Active"
            value={String(analytics?.connections_by_state?.ACTIVE ?? 0)}
            tone="good"
          />
          <Kpi
            label="Success rate"
            value={pct(analytics?.sync_success_rate ?? null)}
            tone="good"
          />
          <Kpi
            label="Failed syncs"
            value={String(analytics?.syncs_failed ?? 0)}
            tone={analytics?.syncs_failed ? "bad" : "default"}
          />
          <Kpi
            label="Errors"
            value={String(analytics?.errors_total ?? 0)}
            tone={analytics?.errors_total ? "bad" : "default"}
          />
          <Kpi label="Events" value={String(analytics?.events_total ?? 0)} />
        </div>
      </section>

      {/* Connected Apps health */}
      <section className="space-y-3">
        <SectionHeading heading="Connected apps" size="md" />
        {connected.length === 0 ? (
          <EmptyState
            icon={Activity}
            title="No apps connected yet"
            description="Connect a provider above to start syncing marketing data."
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {connected.map(({ provider, connection }) => (
              <Surface
                key={provider.slug}
                state={
                  connection?.state === "ACTIVE"
                    ? "good"
                    : connection?.state === "ERROR"
                      ? "bad"
                      : "default"
                }
                padding="compact"
                className="space-y-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{provider.display_name}</span>
                  <StatusPill
                    tone={STATE_TONE[connection!.state]}
                    size="sm"
                    dot
                  >
                    {connection!.state}
                  </StatusPill>
                </div>
                <dl className="space-y-1 text-xs text-muted-foreground">
                  <div className="flex justify-between">
                    <dt>Account</dt>
                    <dd className="text-foreground">
                      {connection!.external_account_name ?? "—"}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Last sync</dt>
                    <dd className="text-foreground">
                      {fmt(connection!.last_sync_at)}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Last error</dt>
                    <dd
                      className={cn(
                        connection!.last_error_at
                          ? "text-bad"
                          : "text-foreground",
                      )}
                    >
                      {fmt(connection!.last_error_at)}
                    </dd>
                  </div>
                </dl>
                {connection!.error_message && (
                  <p className="rounded bg-bad-soft px-2 py-1 text-xs text-bad-soft-foreground">
                    {connection!.error_message}
                  </p>
                )}
              </Surface>
            ))}
          </div>
        )}
      </section>

      {/* Activity log / Sync history / Error center */}
      <section className="space-y-3">
        <SectionHeading
          heading="Activity"
          description="Every OAuth, sync, disconnect, and error event — tenant-scoped."
          size="md"
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                download(
                  `integration-events-${new Date().toISOString().slice(0, 10)}.csv`,
                  toCsv(filtered),
                )
              }
              disabled={filtered.length === 0}
              data-testid="integrations-export"
            >
              <Download className="h-4 w-4" />
              Export CSV
            </Button>
          }
        />

        {/* Tabs + filters */}
        <div className="flex flex-wrap items-center gap-2">
          {(
            [
              ["all", "Activity log", Activity],
              ["sync", "Sync history", CheckCircle2],
              ["errors", "Error center", AlertTriangle],
            ] as const
          ).map(([key, label, Icon]) => (
            <Button
              key={key}
              variant={tab === key ? "default" : "ghost"}
              size="sm"
              onClick={() => setTab(key)}
              data-testid={`integrations-tab-${key}`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Button>
          ))}
          <div className="ml-auto flex items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search events…"
                className="h-8 w-44 pl-8 text-xs"
                data-testid="integrations-search"
              />
            </div>
            <select
              value={providerFilter}
              onChange={(e) => setProviderFilter(e.target.value)}
              className="h-8 rounded-md border border-input bg-background px-2 text-xs"
              data-testid="integrations-provider-filter"
            >
              <option value="">All providers</option>
              {providerOptions.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Table */}
        {filtered.length === 0 ? (
          <EmptyState
            icon={Activity}
            title="No events yet"
            description="Sync a connected app to start building the activity history."
          />
        ) : (
          <Surface padding="none" className="overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-2 font-medium">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 hover:text-foreground"
                      onClick={() => setSortDesc((s) => !s)}
                      data-testid="integrations-sort-time"
                    >
                      Time {sortDesc ? "↓" : "↑"}
                    </button>
                  </th>
                  <th className="px-4 py-2 font-medium">Provider</th>
                  <th className="px-4 py-2 font-medium">Event</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 text-right font-medium">Duration</th>
                  <th className="px-4 py-2 font-medium">Details</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((ev) => (
                  <tr
                    key={ev.id}
                    className="border-b border-border/50 last:border-0"
                  >
                    <td className="whitespace-nowrap px-4 py-2 text-muted-foreground">
                      {fmt(ev.occurred_at)}
                    </td>
                    <td className="px-4 py-2">{ev.provider_slug}</td>
                    <td className="px-4 py-2 font-mono text-xs">
                      {ev.event_type}
                    </td>
                    <td className="px-4 py-2">
                      <StatusPill tone={statusTone(ev.status)} size="sm">
                        {ev.status}
                      </StatusPill>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-muted-foreground">
                      {ev.duration_ms != null ? `${ev.duration_ms}ms` : "—"}
                    </td>
                    <td className="max-w-xs truncate px-4 py-2 text-muted-foreground">
                      {ev.message ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Surface>
        )}

        {/* Pagination */}
        {pageCount > 1 && (
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {filtered.length} event{filtered.length === 1 ? "" : "s"} · page{" "}
              {page + 1} of {pageCount}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= pageCount - 1}
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
