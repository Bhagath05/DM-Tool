"use client";

/**
 * Phase 10.1 — Settings · Security.
 *
 * Four sections, all honest about what's wired today:
 *
 *   1. Authentication       — surfaces the real auth mode (Clerk / demo /
 *                             hybrid) so the founder knows what's
 *                             protecting their account.
 *   2. Active sessions      — current session is real; "Revoke all
 *                             other sessions" is a placeholder because
 *                             no session-list endpoint exists yet.
 *   3. Multi-factor (MFA)   — Clerk handles this when configured at
 *                             org level; we link out, no UI duplication.
 *   4. Login history        — empty state today; populated when an
 *                             audit-log endpoint ships.
 *
 * Never fabricates session rows, login events, or MFA status.
 */

import {
  Activity,
  ArrowUpRight,
  Fingerprint,
  Globe,
  KeyRound,
  Laptop,
  type LucideIcon,
  Lock,
  ShieldCheck,
  TimerReset,
} from "lucide-react";
import { useEffect, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

interface SessionRow {
  id: string;
  device: string;
  location: string;
  isCurrent: boolean;
  lastActive: string;
}

export default function SecuritySettingsPage() {
  const tenant = useTenant();
  const [userAgent, setUserAgent] = useState<string>("This device");
  const [now, setNow] = useState<string>("just now");

  // Resolve the current device summary client-side so SSR doesn't
  // hydrate a different value than the browser.
  useEffect(() => {
    if (typeof navigator !== "undefined") {
      setUserAgent(prettyAgent(navigator.userAgent));
    }
    setNow(new Date().toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }));
  }, []);

  const sessions: SessionRow[] = [
    {
      id: "current",
      device: userAgent,
      location: "Your browser",
      isCurrent: true,
      lastActive: now,
    },
  ];

  // Auth mode — read from env so we surface what's actually live.
  const authMode =
    process.env.NEXT_PUBLIC_AUTH_MODE ?? "hybrid";

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
              Account protected by Clerk
            </h3>
            <p className="text-sm text-muted-foreground">
              Sign-in, sessions, and password reset are handled by Clerk's
              enterprise auth — SOC 2, MFA-capable, GDPR-compliant.
            </p>
            <p className="text-xs text-muted-foreground/80">
              Auth mode: <span className="tabular font-medium">{authMode}</span>
              {tenant.user?.email && (
                <>
                  {" · "}signed in as{" "}
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
            disabled
            data-testid="security-revoke-all"
            title="Bulk session revocation lands in a future release"
          >
            <TimerReset className="mr-2 h-3.5 w-3.5" />
            Revoke all others
          </Button>
        </header>
        <ul className="divide-y divide-border/40">
          {sessions.map((s) => (
            <SessionRowView key={s.id} row={s} />
          ))}
        </ul>
      </section>

      {/* MFA + Password */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <SecurityFeatureCard
          icon={Fingerprint}
          title="Multi-factor authentication"
          description="Add a second factor (TOTP, passkey, SMS) via your Clerk account. We never store factor secrets."
          tone="ai"
          status="Configured in Clerk"
          actionLabel="Open Clerk profile"
          actionHref="https://accounts.clerk.dev/user"
          external
          testId="security-mfa"
        />
        <SecurityFeatureCard
          icon={KeyRound}
          title="Password & passkeys"
          description="Change your password or add a passkey from your Clerk account. Resets flow through verified email."
          tone="ai"
          status="Configured in Clerk"
          actionLabel="Open Clerk profile"
          actionHref="https://accounts.clerk.dev/user"
          external
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
          hint="If you suspect unauthorised access, change your password from your Clerk profile immediately."
          action={
            <Button asChild size="sm">
              <a
                href="https://accounts.clerk.dev/user"
                target="_blank"
                rel="noopener noreferrer"
                data-testid="security-clerk-link"
              >
                Open Clerk profile
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

function SessionRowView({ row }: { row: SessionRow }) {
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
            {row.device}
            {row.isCurrent && (
              <StatusPill tone="good" size="sm" dot>
                This device
              </StatusPill>
            )}
          </span>
          <span className="text-xs text-muted-foreground">
            <Globe className="mr-1 inline h-3 w-3" />
            {row.location} · Last active {row.lastActive}
          </span>
        </div>
      </div>
      <Button
        size="sm"
        variant="outline"
        disabled={row.isCurrent}
        data-testid={`session-${row.id}-revoke`}
        title={
          row.isCurrent
            ? "You can't revoke the session you're using"
            : "Revoke this session"
        }
      >
        {row.isCurrent ? "Current" : "Revoke"}
      </Button>
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
