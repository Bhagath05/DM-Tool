import { Inbox } from "./_components/inbox";
import { PageHeader, PageShell } from "@/components/ui/page-shell";

export const dynamic = "force-dynamic";

export default function LeadsPage() {
  return (
    <PageShell data-testid="leads-page">
      <PageHeader
        title="Who to contact first"
        description="Your leads ranked by who's most worth your time today — with the action to take and what to expect from each."
      />
      <Inbox />
    </PageShell>
  );
}
