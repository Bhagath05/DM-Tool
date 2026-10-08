import { ScheduledPosts } from "./_components/scheduled-posts";
import { SocialIntelligence } from "./_components/social-intelligence";
import { MeasureTabs } from "@/components/brain/measure-tabs";
import { PageHeader, PageShell } from "@/components/ui/page-shell";

export const dynamic = "force-dynamic";

export default function SocialPage() {
  return (
    <PageShell data-testid="social-page">
      <PageHeader
        nav={<MeasureTabs active="social" />}
        title="What actually works on social"
        description="Connect your platforms — or paste in performance data — and the AI extracts the patterns behind your best posts. Every reel, ad, and campaign generated after this inherits those patterns automatically."
      />
      <SocialIntelligence />
      <ScheduledPosts />
    </PageShell>
  );
}
