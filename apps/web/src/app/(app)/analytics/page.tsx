import { Dashboard } from "./_components/dashboard";

export const dynamic = "force-dynamic";

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          How your business is growing
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Who&apos;s coming in, how they found you, and what&apos;s actually
          working. No vanity numbers — just the signals that grow the business.
        </p>
      </div>
      <Dashboard />
    </div>
  );
}
