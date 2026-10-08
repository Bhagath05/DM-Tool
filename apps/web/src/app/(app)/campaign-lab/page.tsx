import { CampaignLab } from "./_components/campaign-lab";
import { MeasureTabs } from "@/components/brain/measure-tabs";
import { PageHeader, PageShell } from "@/components/ui/page-shell";

export const dynamic = "force-dynamic";

export default function CampaignLabPage() {
  return (
    <PageShell data-testid="campaign-lab-page">
      <PageHeader
        nav={<MeasureTabs active="lab" />}
        title="What we've learned from your campaigns"
        description="Every reel, ad, and page we generate is recorded as an experiment. When the results come in, the AI clusters them and surfaces what actually moved the needle — so the next generation inherits a smarter starting point."
      />
      <CampaignLab />
    </PageShell>
  );
}
