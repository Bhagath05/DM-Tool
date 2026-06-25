import { OpportunityCenter } from "./_components/center";

export const dynamic = "force-dynamic";

export default function OpportunitiesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Your opportunities
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          The single most leveraged content and ad moves to make this
          week — with the action to take, what to expect, and a one-click
          jump into the generator.
        </p>
      </div>
      <OpportunityCenter />
    </div>
  );
}
