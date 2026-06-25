import { CampaignLab } from "./_components/campaign-lab";

export const dynamic = "force-dynamic";

export default function CampaignLabPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          What we&apos;ve learned from your campaigns
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every reel, ad, and page we generate is recorded as an experiment.
          When the results come in, the AI clusters them and surfaces what
          actually moved the needle — so the next generation inherits a
          smarter starting point.
        </p>
      </div>
      <CampaignLab />
    </div>
  );
}
