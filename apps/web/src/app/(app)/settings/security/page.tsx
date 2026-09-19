"use client";

/**
 * Settings · Security.
 *
 *   1. Authentication       — first-party account summary (Argon2id, HttpOnly
 *                             session cookie).
 *   2. Active sessions      — real first-party sessions from GET
 *                             /security/sessions; revoke one, revoke all
 *                             others, or sign out the current device.
 *   3. Password             — reset via a verified, single-use email link.
 *   4. Login history        — empty state today; populated when an
 *                             audit-log endpoint ships.
 *
 * Never fabricates session rows or login events.
 */

import {
  Activity,
  ArrowUpRight,
  Globe,
  KeyRound,
  Laptop,
  type LucideIcon,
  Lock,
  ShieldCheck,
  TimerReset,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { api, type SecuritySession } from "@/lib/api";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default function SecuritySettingsPage() {
  const tenant = useTenant();
  const router = useRouter();
  const [sessions, setSessions] = useState<SecuritySession[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refetch = useCallback(async () => {
    try {
      const res = await api.security.sessions();
      setSessions(res.sessions);
    } catch {
      /* settings sub-panel — stay quiet on error */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  async function revokeOne(id: string) {
    setBusy(true);
    try {
      await api.security.revokeSession(id);
      await refetch();
    } finally {
      setBusy(false);
    }
  }

  async function revokeAllOthers() {
    setBusy(true);
    try {
      await api.security.revokeAllOtherSessions();
      await refetch();
    } finally {
      setBusy(false);
    }
  }

  // Revoking the CURRENT session = sign out (the server-side session is
  // revoked and the cookie cleared), then return to the login page.
  async function signOutCurrent() {
    setBusy(true);
    try {
      await api.auth.signout();
    } catch {
      /* fall through to the redirect regardless */
    }
    router.push("/sign-in" as never);
    router.refresh();
  }

  const hasOthers = sessions.some((s) => !s.is_current);

  return (
    <div className="flex flex-col gap-8" data-testid="settings-security">
      <SectionHeading
        eyebrow="Settings · Security"
        heading="Account security"
        description="What's protecting your account, who's signed in, and the controls you can change."
        size="lg"
      />

      {/* Authentication summary — REAL */}
      <article
        data-testid="security-auth"
        className="card-surface flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="flex items-start gap-4">
          <span
            aria-hidden
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-good-soft text-good"
          >
            <ShieldCheck className="h-5 w-5" />
          </span>
          <div className="flex flex-col gap-1">
            <h3 className="text-card-title font-semibold">
              Account security
            </h3>
            <p className="text-sm text-muted-foreground">
              Sign-in, sessions, and password reset are handled by DM Tool.
              Passwords are hashed with Argon2id and never stored in the clear;
              your session lives in a secure, HttpOnly cookie.
            </p>
            <p className="text-xs text-muted-foreground/80">
              {tenant.user?.email && (
                <>
                  Signed in as{" "}
                  <span className="font-medium">{tenant.user.email}</span>
                </>
              )}
            </p>
          </div>
        </div>
        <StatusPill tone="good" size="md" dot>
          Active
        </StatusPill>
      </article>

      {/* Active sessions */}
      <section
        data-testid="security-sessions"
        className="card-surface flex flex-col gap-0 p-0"
      >
        <header className="flex items-center justify-between gap-3 border-b border-border/60 px-6 py-4">
          <div className="flex flex-col gap-0.5">
            <h3 className="text-card-title font-semibold">Active sessions</h3>
            <p className="text-xs text-muted-foreground">
              Devices currently signed in to your account.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={busy || !hasOthers}
            onClick={() => void revokeAllOthers()}
            data-testid="security-revoke-all"
          >
            <TimerReset className="mr-2 h-3.5 w-3.5" />
            Revoke all others
          </Button>
        </header>
        <ul className="divide-y divide-border/40">
          {loading ? (
            <li className="px-6 py-4 text-sm text-muted-foreground">
              Loading sessions…
            </li>
          ) : sessions.length === 0 ? (
            <li className="px-6 py-4 text-sm text-muted-foreground">
              No active sessions.
            </li>
          ) : (
            sessions.map((s) => (
              <SessionRowView
                key={s.id}
                row={s}
                busy={busy}
                onRevoke={() => void revokeOne(s.id)}
                onSignOut={() => void signOutCurrent()}
              />
            ))
          )}
        </ul>
      </section>

      {/* Password */}
      <div className="grid grid-cols-1 gap-4">
        <SecurityFeatureCard
          icon={KeyRound}
          title="Password"
          description="Reset your password any time via a single-use, expiring link sent to your verified email. Changing it signs out every other session."
          tone="ai"
          status="Email-based reset"
          actionLabel="Reset password"
          actionHref="/forgot-password"
          testId="security-password"
        />
      </div>

      {/* Login history */}
      <section
        data-testid="security-login-history"
        className="flex flex-col gap-4"
      >
        <SectionHeading
          eyebrow={
            <span className="inline-flex items-center gap-1.5">
              <Activity className="h-3 w-3" />
              Audit
            </span>
          }
          heading="Login history"
          description="Every sign-in to your account, with device and location. Useful for spotting access you didn't expect."
        />
        <EmptyState
          icon={Lock}
          title="Login history isn't surfaced yet"
          description="We log every authentication event server-side, but the UI to browse them ships with the audit-log work in an upcoming phase."
          hint="If you suspect unauthorised access, reset your password immediately — it signs out every other session."
          action={
            <Button asChild size="sm">
              <a href="/forgot-password" data-testid="security-reset-link">
                Reset password
                <ArrowUpRight className="ml-1.5 h-3.5 w-3.5" />
              </a>
            </Button>
          }
        />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Sub-components
// ---------------------------------------------------------------------

function SessionRowView({
  row,
  busy,
  onRevoke,
  onSignOut,
}: {
  row: SecuritySession;
  busy: boolean;
  onRevoke: () => void;
  onSignOut: () => void;
}) {
  const device = prettyAgent(row.user_agent ?? "");
  const location = row.ip ?? "Unknown location";
  const lastActive = new Date(row.last_seen_at).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
  return (
    <li
      data-testid={`session-${row.id}`}
      className="flex items-center justify-between gap-4 px-6 py-4"
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-muted text-foreground/80"
        >
          <Laptop className="h-4 w-4" />
        </span>
        <div className="flex flex-col">
          <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
            {device}
            {row.is_current && (
              <StatusPill tone="good" size="sm" dot>
                This device
              </StatusPill>
            )}
          </span>
          <span className="text-xs text-muted-foreground">
            <Globe className="mr-1 inline h-3 w-3" />
            {location} · Last active {lastActive}
          </span>
        </div>
      </div>
      {row.is_current ? (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={onSignOut}
          data-testid={`session-${row.id}-signout`}
          title="Sign out this device (revokes the current session)"
        >
          Sign out
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={onRevoke}
          data-testid={`session-${row.id}-revoke`}
          title="Revoke this session"
        >
          Revoke
        </Button>
      )}
    </li>
  );
}

function SecurityFeatureCard({
  icon: Icon,
  title,
  description,
  tone,
  status,
  actionLabel,
  actionHref,
  external = false,
  testId,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  tone: PillTone;
  status: string;
  actionLabel: string;
  actionHref: string;
  external?: boolean;
  testId?: string;
}) {
  return (
    <article
      data-testid={testId}
      className="card-surface card-surface-hover flex flex-col gap-4 p-5 sm:p-6"
    >
      <header className="flex items-start gap-3">
        <span
          aria-hidden
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl",
            tone === "ai" && "bg-ai-soft text-ai",
            tone === "good" && "bg-good-soft text-good",
            tone === "watch" && "bg-watch-soft text-watch",
            tone === "bad" && "bg-bad-soft text-bad",
            (tone === "neutral" || tone === "muted") &&
              "bg-muted text-foreground/80",
          )}
        >
          <Icon className="h-5 w-5" />
        </span>
        <div className="flex flex-col gap-1">
          <h4 className="text-card-title font-semibold">{title}</h4>
          <StatusPill tone={tone} size="sm" dot>
            {status}
          </StatusPill>
        </div>
      </header>
      <p className="text-sm leading-relaxed text-muted-foreground">
        {description}
      </p>
      <div>
        <Button asChild size="sm" variant="outline">
          {external ? (
            <a
              href={actionHref}
              target="_blank"
              rel="noopener noreferrer"
              data-testid={`${testId}-action`}
            >
              {actionLabel}
              <ArrowUpRight className="ml-1.5 h-3.5 w-3.5" />
            </a>
          ) : (
            <a href={actionHref} data-testid={`${testId}-action`}>
              {actionLabel}
            </a>
          )}
        </Button>
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------
//  Pure helpers
// ---------------------------------------------------------------------

function prettyAgent(ua: string): string {
  // Cheap, no-deps user-agent summary. Good enough for "Chrome on Mac"
  // labelling. A real parser is overkill for one row.
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /Chrome\//.test(ua)
      ? "Chrome"
      : /Safari\//.test(ua)
        ? "Safari"
        : /Firefox\//.test(ua)
          ? "Firefox"
          : "Browser";
  const os = /Mac OS X|Macintosh/.test(ua)
    ? "Mac"
    : /Windows/.test(ua)
      ? "Windows"
      : /Linux/.test(ua)
        ? "Linux"
        : /Android/.test(ua)
          ? "Android"
          : /iPhone|iPad|iOS/.test(ua)
            ? "iOS"
            : "device";
  return `${browser} on ${os}`;
}
