import { HistoryPage } from "./_components/history-page";

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
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
