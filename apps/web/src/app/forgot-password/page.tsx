"use client";

import { useState } from "react";

import { AuthShell } from "@/components/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    try {
      await api.auth.requestPasswordReset(email);
    } catch {
      // Enumeration-safe: never reveal whether the account exists.
    }
    setDone(true);
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle="We'll email you a secure reset link."
      altPrompt="Remembered it?"
      altHref="/sign-in"
      altLabel="Back to sign in"
    >
      {done ? (
        <div
          role="status"
          className="w-full max-w-sm rounded-lg border border-border bg-card p-5 text-sm"
        >
          <p className="font-medium">Check your email</p>
          <p className="mt-1 text-muted-foreground">
            If an account exists for that email, we&apos;ve sent a reset link.
            It expires shortly and can be used once.
          </p>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="flex w-full max-w-sm flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={pending} className="w-full">
            {pending ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
