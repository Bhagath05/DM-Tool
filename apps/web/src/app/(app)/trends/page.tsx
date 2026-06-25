import { TrendReportPanel } from "./_components/report-panel";

export const dynamic = "force-dynamic";

export default function TrendsPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          What&apos;s trending right now
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Live signals from the public web, connected back to your business —
          so you know what to ride and what to post about next.
        </p>
      </div>
      <TrendReportPanel />
    </div>
  );
}
