"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AuthShell } from "@/components/auth-shell";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

type State = "verifying" | "ok" | "error";

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailInner />
    </Suspense>
  );
}

function VerifyEmailInner() {
  const params = useSearchParams();
  const [state, setState] = useState<State>("verifying");

  useEffect(() => {
    const token = params.get("token");
    if (!token) {
      setState("error");
      return;
    }
    let alive = true;
    void api.auth
      .verifyEmail(token)
      .then(() => alive && setState("ok"))
      .catch(() => alive && setState("error"));
    return () => {
      alive = false;
    };
  }, [params]);

  return (
    <AuthShell
      title="Verify your email"
      subtitle="Confirming your account."
      altPrompt="Need to sign in?"
      altHref="/sign-in"
      altLabel="Sign in"
    >
      <div className="w-full max-w-sm space-y-4 text-sm">
        {state === "verifying" && (
          <p className="text-muted-foreground">Verifying…</p>
        )}
        {state === "ok" && (
          <>
            <p className="font-medium">Email verified.</p>
            <p className="text-muted-foreground">
              Your account is active. You can sign in now.
            </p>
            <Button asChild className="w-full">
              <Link href={"/sign-in" as never}>Continue to sign in</Link>
            </Button>
          </>
        )}
        {state === "error" && (
          <>
            <p className="font-medium">This link is invalid or has expired.</p>
            <p className="text-muted-foreground">
              Verification links are single-use and time-limited. Sign in to
              request a new one.
            </p>
            <Button asChild variant="outline" className="w-full">
              <Link href={"/sign-in" as never}>Back to sign in</Link>
            </Button>
          </>
        )}
      </div>
    </AuthShell>
  );
}
