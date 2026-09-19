"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/**
 * Topbar identity + sign-out. First-party: the signed-in user comes from the
 * tenant context (resolved via GET /me), and sign-out revokes the server-side
 * session and clears the cookie, then returns to /sign-in.
 */
export function UserMenu() {
  const router = useRouter();
  const { user } = useTenant();
  const [pending, setPending] = useState(false);

  async function signOut() {
    setPending(true);
    try {
      await api.auth.signout();
    } catch {
      // Even if the call fails, drop the client and send them to sign-in.
    }
    router.push("/sign-in" as never);
    router.refresh();
  }

  const label = user?.display_name || user?.email || "Account";

  return (
    <div className="flex items-center gap-2" data-testid="user-menu">
      <span className="hidden text-sm text-muted-foreground sm:inline" title={user?.email ?? undefined}>
        {label}
      </span>
      <Button
        variant="outline"
        size="sm"
        onClick={signOut}
        disabled={pending}
        data-testid="sign-out"
      >
        {pending ? "Signing out…" : "Sign out"}
      </Button>
    </div>
  );
}
