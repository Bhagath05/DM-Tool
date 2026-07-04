import { ExecutiveDashboard } from "./_components/executive-dashboard";

export const dynamic = "force-dynamic";

export default function CrmDashboardPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Executive Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Pipeline, forecast, team performance, and AI insights — the whole sales
          operation, built on your live CRM data.
        </p>
      </div>
      <ExecutiveDashboard />
    </div>
  );
}
