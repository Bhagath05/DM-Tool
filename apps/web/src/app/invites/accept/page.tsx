"use client";

/**
 * Invite acceptance — /invites/accept?token=…
 *
 * Lives OUTSIDE the (app) route group so the invitee (who may have zero
 * memberships) isn't wrapped by TenantProvider and bounced to onboarding.
 * The route is also marked public in middleware so a logged-out invitee
 * can preview the invite before signing in.
 *
 * Flow:
 *   1. Preview — GET /invites/{token} (public). Shows which org + role
 *      the link grants. Expired links are surfaced here, up front.
 *   2. Accept — POST /invites/accept (requires a signed-in user). On
 *      success we persist the new org/brand selection and redirect to
 *      the backend-suggested route (the dashboard).
 *
 * Revoked / already-accepted / email-mismatch invites can't be detected
 * from the public preview, so they surface as a clear message when the
 * user clicks Accept (the backend returns a precise reason).
 *
 * Organization isolation + RBAC are enforced entirely server-side: the
 * accept endpoint creates the membership + role assignment under the
 * invite's own org and the inviter's granted role. This page never
 * chooses an org or role.
 */

import { SignedIn, SignedOut } from "@clerk/nextjs";
import { AlertCircle, CheckCircle2, Clock, Mail, ShieldX } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { isClerkActive } from "@/lib/clerk-config";
import { api, type InvitePreview } from "@/lib/api";
import { writePersistedSelection } from "@/lib/tenant";

export const dynamic = "force-dynamic";

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={<Shell>Loading invitation…</Shell>}>
      <AcceptInvite />
    </Suspense>
  );
}

function AcceptInvite() {
  const params = useSearchParams();
  const router = useRouter();
  const token = (params.get("token") ?? "").trim();

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [accepting, setAccepting] = useState(false);
  const [acceptError, setAcceptError] = useState<string | null>(null);
  const [joined, setJoined] = useState(false);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      setLoadError("This invitation link is missing its token.");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await api.team.previewInvite(token);
        if (!cancelled) setPreview(res);
      } catch {
        if (!cancelled)
          setLoadError(
            "This invitation link is invalid or no longer exists. Ask your teammate to send a new one.",
          );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleAccept = useCallback(async () => {
    setAccepting(true);
    setAcceptError(null);
    try {
      const res = await api.team.acceptInvite(token);
      // Seed the tenant selection so the dashboard cold-boots into the
      // newly-joined org/brand instead of re-resolving from scratch.
      writePersistedSelection({
        organization_id: res.organization_id,
        brand_id: res.brand_id,
      });
      setJoined(true);
      // next_route is a backend-supplied path; typedRoutes can't infer it.
      router.push((res.next_route || "/dashboard") as never);
    } catch (e) {
      setAcceptError(
        e instanceof Error
          ? e.message
          : "We couldn't accept this invitation. Please try again.",
      );
      setAccepting(false);
    }
  }, [token, router]);

  if (loading) {
    return <Shell>Loading invitation…</Shell>;
  }

  if (loadError) {
    return (
      <Shell>
        <StateCard
          icon={<ShieldX className="h-6 w-6 text-bad" />}
          title="Invitation unavailable"
          body={loadError}
          footer={
            <Button asChild variant="outline" size="sm">
              <Link href="/">Go to home</Link>
            </Button>
          }
        />
      </Shell>
    );
  }

  if (!preview) return <Shell>Loading invitation…</Shell>;

  if (preview.is_expired) {
    return (
      <Shell>
        <StateCard
          icon={<Clock className="h-6 w-6 text-watch" />}
          title="This invitation has expired"
          body={`The invite to join ${preview.organization_name} as ${preview.role_display_name} is no longer valid. Ask for a fresh invitation.`}
          footer={
            <Button asChild variant="outline" size="sm">
              <Link href="/">Go to home</Link>
            </Button>
          }
        />
      </Shell>
    );
  }

  if (joined) {
    return (
      <Shell>
        <StateCard
          icon={<CheckCircle2 className="h-6 w-6 text-good" />}
          title={`You've joined ${preview.organization_name}`}
          body="Taking you to your workspace…"
        />
      </Shell>
    );
  }

  // After signing in, Clerk returns the user to this exact invite via the
  // `redirect_url` query param (Next encodes the value for the href).
  const redirectTarget = `/invites/accept?token=${token}`;

  return (
    <Shell>
      <div
        data-testid="invite-accept-card"
        className="card-surface flex w-full flex-col gap-5 p-6 sm:p-8"
      >
        <div className="flex flex-col items-center gap-3 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-ai-soft text-ai">
            <Mail className="h-6 w-6" />
          </span>
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold tracking-tight">
              Join {preview.organization_name}
            </h1>
            <p className="text-sm text-muted-foreground">
              You&apos;ve been invited to join as{" "}
              <span className="font-medium text-foreground">
                {preview.role_display_name}
              </span>
              .
            </p>
          </div>
        </div>

        <dl className="flex flex-col gap-2 rounded-xl border border-border/60 bg-muted/30 p-4 text-sm">
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">Workspace</dt>
            <dd className="font-medium text-foreground">
              {preview.organization_name}
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">Your role</dt>
            <dd className="font-medium text-foreground">
              {preview.role_display_name}
            </dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted-foreground">Invited email</dt>
            <dd className="truncate font-medium text-foreground">
              {preview.invited_email}
            </dd>
          </div>
        </dl>

        {!isClerkActive() ? (
          <p className="text-center text-sm text-muted-foreground">
            Accepting an invitation requires a signed-in account.
          </p>
        ) : (
          <>
            <SignedIn>
              {acceptError && <ErrorLine message={acceptError} />}
              <Button
                className="w-full"
                onClick={() => void handleAccept()}
                disabled={accepting}
                data-testid="invite-accept-button"
              >
                {accepting ? "Joining…" : "Accept invitation"}
              </Button>
            </SignedIn>
            <SignedOut>
              <Button asChild className="w-full">
                <Link
                  href={{
                    pathname: "/sign-in",
                    query: { redirect_url: redirectTarget },
                  }}
                  data-testid="invite-signin-link"
                >
                  Sign in to accept
                </Link>
              </Button>
              <p className="text-center text-xs text-muted-foreground">
                Sign in with {preview.invited_email} to join this workspace.
              </p>
            </SignedOut>
          </>
        )}
      </div>
    </Shell>
  );
}

// ---------------------------------------------------------------------
//  Presentation helpers
// ---------------------------------------------------------------------

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-md">
        {typeof children === "string" ? (
          <p className="text-center text-sm text-muted-foreground">
            {children}
          </p>
        ) : (
          children
        )}
      </div>
    </main>
  );
}

function StateCard({
  icon,
  title,
  body,
  footer,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  footer?: React.ReactNode;
}) {
  return (
    <div className="card-surface flex flex-col items-center gap-4 p-6 text-center sm:p-8">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
        {icon}
      </span>
      <div className="flex flex-col gap-1.5">
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        <p className="text-sm leading-relaxed text-muted-foreground">{body}</p>
      </div>
      {footer}
    </div>
  );
}

function ErrorLine({ message }: { message: string }) {
  return (
    <p
      role="alert"
      className="flex items-start gap-2 rounded-lg border border-bad-border bg-bad-soft/40 px-3 py-2 text-sm text-bad-soft-foreground"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      {message}
    </p>
  );
}
