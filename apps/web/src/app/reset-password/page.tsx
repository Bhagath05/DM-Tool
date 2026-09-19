"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthShell } from "@/components/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordInner />
    </Suspense>
  );
}

function ResetPasswordInner() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await api.auth.resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "This reset link is invalid or has expired.",
      );
      setPending(false);
    }
  }

  return (
    <AuthShell
      title="Choose a new password"
      subtitle="Set a new password for your account."
      altPrompt="Back to"
      altHref="/sign-in"
      altLabel="Sign in"
    >
      {done ? (
        <div
          role="status"
          className="w-full max-w-sm space-y-4 rounded-lg border border-border bg-card p-5 text-sm"
        >
          <p className="font-medium">Password changed.</p>
          <p className="text-muted-foreground">
            For your security, all existing sessions were signed out. Sign in
            with your new password.
          </p>
          <Button asChild className="w-full">
            <Link href={"/sign-in" as never}>Continue to sign in</Link>
          </Button>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="flex w-full max-w-sm flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">New password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={10}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              At least 10 characters.
            </p>
          </div>
          {!token && (
            <p role="alert" className="text-sm text-bad">
              Missing reset token — use the link from your email.
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm text-bad">
              {error}
            </p>
          )}
          <Button
            type="submit"
            disabled={pending || !token}
            className="w-full"
          >
            {pending ? "Saving…" : "Set new password"}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
