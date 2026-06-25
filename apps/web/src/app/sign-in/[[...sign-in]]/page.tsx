"use client";

import Link from "next/link";

import { SignIn } from "@clerk/nextjs";

import { Button } from "@/components/ui/button";
import { getAuthMode, isClerkActive } from "@/lib/clerk-config";

export default function SignInPage() {
  // <SignIn /> internally calls useSession(), which throws when
  // <ClerkProvider /> isn't mounted. Mode-aware render:
  //   - clerk-active     → real Clerk UI
  //   - demo (intentional) or clerk-misconfigured → friendly fallback
  if (!isClerkActive()) {
    return <Fallback action="sign in" />;
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignIn />
    </div>
  );
}

function Fallback({ action }: { action: string }) {
  const mode = getAuthMode();
  const isDemo = mode === "demo";

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="max-w-md space-y-4 rounded-lg border border-border bg-card p-6 text-center">
        <h1 className="text-xl font-semibold">
          {isDemo ? "Demo mode" : "Auth not configured"}
        </h1>
        {isDemo ? (
          <>
            <p className="text-sm text-muted-foreground">
              Sign-in is disabled while the app is in demo mode. Open the
              dashboard directly to explore the product — no account
              needed.
            </p>
            <Button asChild>
              <Link href={"/dashboard" as never}>Open dashboard</Link>
            </Button>
            <p className="text-xs text-muted-foreground">
              To enable real authentication, set{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                AUTH_MODE=clerk
              </code>{" "}
              in both <code className="rounded bg-muted px-1 py-0.5 text-xs">.env</code>{" "}
              and{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                apps/web/.env.local
              </code>{" "}
              and restart.
            </p>
          </>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Clerk publishable + secret keys aren&apos;t set, so the{" "}
              {action} form can&apos;t render. Set the four{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                CLERK_*
              </code>{" "}
              variables in{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">.env</code>{" "}
              and restart{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                pnpm dev
              </code>
              .
            </p>
            <p className="text-xs text-muted-foreground">
              Get keys at{" "}
              <a
                href="https://dashboard.clerk.com"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                dashboard.clerk.com
              </a>
              .
            </p>
          </>
        )}
      </div>
    </div>
  );
}
