import { HistoryPage } from "./_components/history-page";
import { MeasureTabs } from "@/components/brain/measure-tabs";
import { PageHeader, PageShell } from "@/components/ui/page-shell";

export default function Page() {
  return (
    <PageShell data-testid="history-page">
      <PageHeader
        nav={<MeasureTabs active="history" />}
        title="What the AI recommended, and how it turned out"
        description="Recommendations your advisor made, what you completed, and what actually worked."
      />
      <HistoryPage />
    </PageShell>
  );
}
