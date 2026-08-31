import Link from "next/link";

import { Button } from "@/components/ui/button";
import { isAuthEnforced } from "@/lib/clerk-config";

export default function HomePage() {
  // Production runs AUTH_MODE=clerk (isAuthEnforced). There is NO anonymous
  // entry: the public CTA routes to Clerk sign-up / sign-in. In local
  // demo/hybrid dev only, the "Open dashboard" shortcut is kept for
  // developer convenience.
  const clerkOnly = isAuthEnforced();
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6">
      <div className="max-w-xl space-y-6 text-center">
        <h1 className="text-4xl font-bold tracking-tight">
          Your AI digital marketing advisor
        </h1>
        <p className="text-muted-foreground">
          Know exactly what to post, which ad to run, and who to follow up with
          — every day. No marketing background required.
        </p>
        <div className="flex justify-center gap-3">
          {clerkOnly ? (
            <>
              <Button asChild size="lg">
                <Link href={"/sign-up" as never}>Get started</Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link href={"/sign-in" as never}>Sign in</Link>
              </Button>
            </>
          ) : (
            <>
              <Button asChild size="lg">
                <Link href={"/dashboard" as never}>Open dashboard</Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link href={"/sign-in" as never}>Sign in</Link>
              </Button>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
