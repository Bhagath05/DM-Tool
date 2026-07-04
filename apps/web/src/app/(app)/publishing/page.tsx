import { PublishingDashboard } from "./_components/publishing-dashboard";

export const dynamic = "force-dynamic";

export default function PublishingPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Publishing</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Review, approve, schedule, and publish every asset across your
          connected platforms — with retry, backoff, and platform health built in.
        </p>
      </div>
      <PublishingDashboard />
    </div>
  );
}
