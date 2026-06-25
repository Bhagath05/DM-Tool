import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function HomePage() {
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
          <Button asChild size="lg">
            <Link href={"/dashboard" as never}>Open dashboard</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href={"/sign-in" as never}>Sign in</Link>
          </Button>
        </div>
      </div>
    </main>
  );
}
