"use client";

/**
 * Phase 6.4 — Publishing dashboard.
 *
 * Enterprise view over the live /publishing API: queue analytics, platform
 * health, and a queue with per-post lifecycle actions (cancel / pause / resume
 * / retry) + the approval gate (submit / approve / reject / request changes)
 * gated by each post's state. Design system reused throughout.
 */

import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Pause,
  Play,
  RotateCcw,
  Send,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { Surface } from "@/components/ui/surface";
import {
  api,
  type ApprovalStatus,
  type PublishStatus,
  type QueueAnalytics,
  type ScheduledPost,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<PublishStatus, PillTone> = {
  draft: "neutral",
  scheduled: "watch",
  publishing: "ai",
  published: "good",
  failed: "bad",
  cancelled: "muted",
  paused: "muted",
};

const APPROVAL_TONE: Record<ApprovalStatus, PillTone> = {
  not_required: "muted",
  pending: "watch",
  approved: "good",
  rejected: "bad",
  changes_requested: "watch",
};

function humanize(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function fmtSeconds(s: number | null): string {
  if (s == null) return "—";
  if (s < 90) return `${Math.round(s)}s`;
  if (s < 5400) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: PillTone }) {
  return (
    <Surface padding="compact" className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("text-2xl font-semibold", tone === "bad" && "text-bad", tone === "good" && "text-good")}>
        {value}
      </span>
    </Surface>
  );
}

const STATUS_FILTERS: (PublishStatus | "all")[] = [
  "all", "scheduled", "published", "failed", "paused", "cancelled",
];

export function PublishingDashboard() {
  const [analytics, setAnalytics] = useState<QueueAnalytics | null>(null);
  const [posts, setPosts] = useState<ScheduledPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [filter, setFilter] = useState<PublishStatus | "all">("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [a, p] = await Promise.all([
        api.publishing.analytics(),
        api.publishing.calendar(),
      ]);
      setAnalytics(a);
      setPosts(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load the publishing queue.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (id: string, fn: () => Promise<ScheduledPost>) => {
    setBusyId(id);
    setError(null);
    try {
      const updated = await fn();
      setPosts((prev) => prev.map((x) => (x.id === id ? updated : x)));
      void api.publishing.analytics().then(setAnalytics).catch(() => {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed.");
    } finally {
      setBusyId(null);
    }
  };

  const filtered = useMemo(
    () => (filter === "all" ? posts : posts.filter((p) => p.publish_status === filter)),
    [posts, filter],
  );

  const postActions = (p: ScheduledPost) => {
    const busy = busyId === p.id;
    const P = api.publishing;
    const actions: React.ReactNode[] = [];
    const btn = (key: string, label: string, Icon: typeof Play, fn: () => Promise<ScheduledPost>, danger = false) => (
      <Button
        key={key}
        size="sm"
        variant={danger ? "destructive" : "outline"}
        disabled={busy}
        onClick={() => void act(p.id, fn)}
      >
        <Icon className="h-3.5 w-3.5" />
        {label}
      </Button>
    );

    if (p.approval_status === "pending") {
      actions.push(btn("approve", "Approve", CheckCircle2, () => P.approve(p.id)));
      actions.push(btn("changes", "Changes", RotateCcw, () => P.requestChanges(p.id)));
      actions.push(btn("reject", "Reject", X, () => P.reject(p.id), true));
    }
    if (["scheduled", "failed"].includes(p.publish_status) && p.approval_status !== "pending") {
      actions.push(btn("pause", "Pause", Pause, () => P.pause(p.id)));
    }
    if (p.publish_status === "paused") {
      actions.push(btn("resume", "Resume", Play, () => P.resume(p.id)));
    }
    if (p.publish_status === "failed") {
      actions.push(btn("retry", "Retry", RotateCcw, () => P.retry(p.id)));
    }
    if (p.approval_status === "not_required" && ["scheduled", "draft"].includes(p.publish_status)) {
      actions.push(btn("submit", "Submit for approval", Send, () => P.submitForApproval(p.id)));
    }
    if (!["published", "cancelled"].includes(p.publish_status)) {
      actions.push(btn("cancel", "Cancel", X, () => P.cancel(p.id), true));
    }
    return actions;
  };

  return (
    <div className="space-y-6" data-testid="publishing-dashboard">
      <SectionHeading
        eyebrow="Publishing"
        heading="Queue, approvals & platform health"
        description="Every scheduled post — review, approve, pause, retry, and track publishing across platforms."
        action={
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <Clock className="h-4 w-4" />
            Refresh
          </Button>
        }
      />

      {error && (
        <Surface state="bad" padding="compact" className="text-sm text-bad">
          {error}
        </Surface>
      )}

      {/* Analytics */}
      {loading ? (
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : analytics ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Published" value={analytics.published} tone="good" />
            <Stat label="Scheduled" value={analytics.scheduled} />
            <Stat label="Queue length" value={analytics.queue_length} />
            <Stat label="Failed" value={analytics.failed} tone={analytics.failed ? "bad" : undefined} />
            <Stat label="Success rate" value={`${Math.round(analytics.success_rate * 100)}%`} />
            <Stat label="Avg publish" value={fmtSeconds(analytics.avg_publish_seconds)} />
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            {analytics.approval_pending > 0 && (
              <StatusPill tone="watch" size="sm">
                {analytics.approval_pending} awaiting approval
              </StatusPill>
            )}
            {analytics.paused > 0 && (
              <StatusPill tone="muted" size="sm">{analytics.paused} paused</StatusPill>
            )}
            {analytics.total_retries > 0 && (
              <span>{analytics.total_retries} total retries</span>
            )}
          </div>

          {/* Platform health */}
          {analytics.platform_health.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {analytics.platform_health.map((h) => (
                <Surface key={h.platform} padding="compact" className="flex items-center gap-2">
                  <span className="text-sm font-medium">{humanize(h.platform)}</span>
                  <StatusPill
                    tone={h.failed > 0 && h.success_rate < 0.8 ? "bad" : "good"}
                    size="sm"
                  >
                    {Math.round(h.success_rate * 100)}% ok
                  </StatusPill>
                  {h.failed > 0 && (
                    <span className="flex items-center gap-1 text-xs text-bad">
                      <AlertTriangle className="h-3 w-3" />
                      {h.failed}
                    </span>
                  )}
                </Surface>
              ))}
            </div>
          )}
        </>
      ) : null}

      {/* Filter */}
      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map((s) => (
          <Button
            key={s}
            size="sm"
            variant={filter === s ? "default" : "ghost"}
            onClick={() => setFilter(s)}
          >
            {s === "all" ? "All" : humanize(s)}
          </Button>
        ))}
      </div>

      {/* Queue */}
      {loading ? (
        <Skeleton className="h-40 w-full" />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Send}
          title="Nothing in the queue"
          description="Schedule content from the Content or Creative Studio to see it here."
        />
      ) : (
        <div className="space-y-2">
          {filtered.map((p) => (
            <Surface key={p.id} padding="compact" className="flex flex-col gap-2" data-testid="queue-post">
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill tone="neutral" size="sm">{humanize(p.platform)}</StatusPill>
                <StatusPill tone={STATUS_TONE[p.publish_status]} size="sm">
                  {humanize(p.publish_status)}
                </StatusPill>
                {p.approval_status !== "not_required" && (
                  <StatusPill tone={APPROVAL_TONE[p.approval_status]} size="sm">
                    {humanize(p.approval_status)}
                  </StatusPill>
                )}
                <span className="text-xs text-muted-foreground">
                  {new Date(p.scheduled_at).toLocaleString()}
                </span>
                {p.attempt_count > 0 && (
                  <span className="text-xs text-muted-foreground">· {p.attempt_count} attempt{p.attempt_count > 1 ? "s" : ""}</span>
                )}
                {p.published_at && (
                  <span className="ml-auto text-xs text-good">Live</span>
                )}
              </div>
              {p.error_message && (
                <p className="text-xs text-bad">{p.error_message}</p>
              )}
              {p.approval_reason && (
                <p className="text-xs text-muted-foreground">Reviewer: {p.approval_reason}</p>
              )}
              <div className="flex flex-wrap gap-1.5">{postActions(p)}</div>
            </Surface>
          ))}
        </div>
      )}
    </div>
  );
}
