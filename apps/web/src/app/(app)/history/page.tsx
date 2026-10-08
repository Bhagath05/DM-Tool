import { HistoryPage } from "./_components/history-page";
import { MeasureTabs } from "@/components/brain/measure-tabs";

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <MeasureTabs active="history" />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">AI History</h1>
        <p className="text-sm text-muted-foreground">
          Recommendations your advisor made, what you completed, and what worked.
        </p>
      </div>
      <HistoryPage />
    </div>
  );
}
