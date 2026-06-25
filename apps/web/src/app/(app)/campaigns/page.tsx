import { Studio } from "./_components/studio";

export const dynamic = "force-dynamic";

export default function CampaignsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Campaign planner
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Build a multi-day plan that sequences platforms, posts and ad
          support across a funnel. Each calendar day is a brief — generate
          the actual content/ad/visual later from the matching studio.
        </p>
      </div>
      <Studio />
    </div>
  );
}
