import { Inbox } from "./_components/inbox";

export const dynamic = "force-dynamic";

export default function LeadsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Who to contact first
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your leads ranked by who&apos;s most worth your time today —
          with the action to take and what to expect from each.
        </p>
      </div>
      <Inbox />
    </div>
  );
}
