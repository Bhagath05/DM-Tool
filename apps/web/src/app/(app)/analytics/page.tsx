import { Dashboard } from "./_components/dashboard";
import { MeasureTabs } from "@/components/brain/measure-tabs";
import { PageHeader, PageShell } from "@/components/ui/page-shell";

export const dynamic = "force-dynamic";

export default function AnalyticsPage() {
  return (
    <PageShell data-testid="analytics-page">
      <PageHeader
        nav={<MeasureTabs active="analytics" />}
        title="How your business is growing"
        description="Who's coming in, how they found you, and what's actually working. No vanity numbers — just the signals that grow the business."
      />
      <Dashboard />
    </PageShell>
  );
}
