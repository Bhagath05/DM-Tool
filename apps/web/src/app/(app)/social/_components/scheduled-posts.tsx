"use client";

/**
 * Scheduled Posts — surfaces the publishing pipeline (GET /publishing/calendar)
 * that previously had no UI. Shows each post's platform, time, and lifecycle
 * status; lets an authorized user publish-now or retry a failed post; and
 * exposes the audit trail (GET /publishing/posts/{id}/events).
 *
 * RBAC: read for anyone on the page; publish/retry actions only render with
 * content.create. Tenant isolation is enforced server-side (brand-scoped).
 */

import {
  AlertCircle,
  CheckCircle2,
  Clock,
  History,
  RotateCw,
  Send,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonTable } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import {
  api,
  type PublishEvent,
  type PublishStatus,
  type ScheduledPost,
} from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "ready"; posts: ScheduledPost[] }
  | { kind: "error"; message: string };

export function ScheduledPosts() {
  const { can } = useTenant();
  const canPublish = can("content.create");
  const [state, setState] = useState<State>({ kind: "loading" });
  const [busyId, setBusyId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      setState({ kind: "ready", posts: await api.publishing.calendar() });
    } catch (e) {
      setState({
        kind: "error",
        message:
          e instanceof Error
            ? e.message
            : "We couldn't load your scheduled posts.",
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const runAction = useCallback(
    async (id: string, fn: (id: string) => Promise<ScheduledPost>) => {
      setBusyId(id);
      setActionError(null);
      try {
        await fn(id);
        await load();
      } catch (e) {
        setActionError(
          e instanceof Error ? e.message : "That action didn't go through.",
        );
      } finally {
        setBusyId(null);
      }
    },
    [load],
  );

  return (
    <section className="flex flex-col gap-4" data-testid="scheduled-posts">
      <SectionHeading
        heading="Scheduled & published posts"
        description="Every post you've lined up — when it goes out, whether it published, and what to do if something failed."
      />

      {actionError && (
        <p
          role="alert"
          className="flex items-center gap-2 text-sm text-bad-soft-foreground"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          {actionError}
        </p>
      )}

      {state.kind === "loading" ? (
        <SkeletonTable rows={3} />
      ) : state.kind === "error" ? (
        <div
          data-testid="scheduled-posts-error"
          className="flex flex-col items-start gap-3 rounded-2xl border border-bad-border bg-bad-soft/30 p-5"
        >
          <p className="text-sm text-bad-soft-foreground">{state.message}</p>
          <Button size="sm" variant="outline" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      ) : state.posts.length === 0 ? (
        <EmptyState
          icon={Clock}
          title="No posts scheduled yet"
          description="When you schedule content to a connected platform, it shows up here with its status — and we publish it automatically at the right time."
          data-testid="scheduled-posts-empty"
        />
      ) : (
        <ul className="flex flex-col divide-y divide-border/60">
          {state.posts.map((post) => (
            <PostRow
              key={post.id}
              post={post}
              canPublish={canPublish}
              busy={busyId === post.id}
              expanded={expanded === post.id}
              onToggleHistory={() =>
                setExpanded((cur) => (cur === post.id ? null : post.id))
              }
              onPublishNow={() => void runAction(post.id, api.publishing.publishNow)}
              onRetry={() => void runAction(post.id, api.publishing.retry)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function PostRow({
  post,
  canPublish,
  busy,
  expanded,
  onToggleHistory,
  onPublishNow,
  onRetry,
}: {
  post: ScheduledPost;
  canPublish: boolean;
  busy: boolean;
  expanded: boolean;
  onToggleHistory: () => void;
  onPublishNow: () => void;
  onRetry: () => void;
}) {
  const st = STATUS[post.publish_status];
  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"
            aria-hidden
          >
            <st.icon className="h-4 w-4" />
          </span>
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-medium text-foreground">
              {PLATFORM_LABEL[post.platform] ?? post.platform}
            </span>
            <span className="text-xs text-muted-foreground">
              {post.publish_status === "published" && post.published_at
                ? `Published ${formatDate(post.published_at)}`
                : `Scheduled for ${formatDate(post.scheduled_at)}`}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill tone={st.tone} size="sm" dot>
            {st.label}
          </StatusPill>
          <Button
            size="sm"
            variant="ghost"
            onClick={onToggleHistory}
            aria-label="View publish history"
            aria-expanded={expanded}
          >
            <History className="h-3.5 w-3.5" />
            History
          </Button>
          {canPublish && post.publish_status !== "published" && (
            <Button
              size="sm"
              variant={post.publish_status === "failed" ? "outline" : "default"}
              onClick={post.publish_status === "failed" ? onRetry : onPublishNow}
              disabled={busy}
            >
              {post.publish_status === "failed" ? (
                <>
                  <RotateCw className="h-3.5 w-3.5" />
                  {busy ? "Retrying…" : "Retry"}
                </>
              ) : (
                <>
                  <Send className="h-3.5 w-3.5" />
                  {busy ? "Publishing…" : "Publish now"}
                </>
              )}
            </Button>
          )}
        </div>
      </div>

      {post.publish_status === "failed" && post.error_message && (
        <p className="rounded-md bg-bad-soft/40 px-3 py-2 text-xs text-bad-soft-foreground">
          {post.error_message}
          {post.attempt_count > 0 && (
            <span className="ml-1 opacity-70">
              ({post.attempt_count} attempt{post.attempt_count === 1 ? "" : "s"})
            </span>
          )}
        </p>
      )}

      {expanded && <PostHistory postId={post.id} />}
    </li>
  );
}

function PostHistory({ postId }: { postId: string }) {
  const [events, setEvents] = useState<PublishEvent[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.publishing
      .events(postId)
      .then((e) => {
        if (!cancelled) setEvents(e);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [postId]);

  if (error) {
    return (
      <p className="pl-11 text-xs text-muted-foreground">
        Couldn&apos;t load the history for this post.
      </p>
    );
  }
  if (events === null) {
    return <p className="pl-11 text-xs text-muted-foreground">Loading history…</p>;
  }
  if (events.length === 0) {
    return <p className="pl-11 text-xs text-muted-foreground">No history yet.</p>;
  }

  return (
    <ol
      data-testid="post-history"
      className="ml-11 flex flex-col gap-1 border-l border-border/60 pl-4 text-xs"
    >
      {events.map((ev) => (
        <li key={ev.id} className="flex items-center gap-2 text-muted-foreground">
          <span className="font-medium text-foreground">
            {EVENT_LABEL[ev.event_type] ?? ev.event_type}
          </span>
          <span className="opacity-70">{formatDateTime(ev.created_at)}</span>
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------------
//  Config + helpers
// ---------------------------------------------------------------------

const STATUS: Record<
  PublishStatus,
  { label: string; tone: PillTone; icon: typeof Clock }
> = {
  draft: { label: "Draft", tone: "neutral", icon: Clock },
  scheduled: { label: "Scheduled", tone: "watch", icon: Clock },
  publishing: { label: "Publishing", tone: "ai", icon: Clock },
  published: { label: "Published", tone: "good", icon: CheckCircle2 },
  failed: { label: "Failed", tone: "bad", icon: XCircle },
  cancelled: { label: "Cancelled", tone: "muted", icon: XCircle },
  paused: { label: "Paused", tone: "muted", icon: Clock },
};

const PLATFORM_LABEL: Record<string, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  linkedin: "LinkedIn",
  youtube: "YouTube",
  pinterest: "Pinterest",
  google_business_profile: "Google Business Profile",
};

const EVENT_LABEL: Record<string, string> = {
  scheduled: "Scheduled",
  publish_attempt: "Publish attempt",
  published: "Published",
  failed: "Failed",
  retry_requested: "Retry requested",
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
