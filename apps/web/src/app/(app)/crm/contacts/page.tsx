import { CrmDirectory } from "./_components/crm-directory";

export const dynamic = "force-dynamic";

export default function CrmContactsPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Contacts &amp; Companies</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          The people and organizations behind your deals — with merge, timeline,
          and AI summaries grounded in real CRM data.
        </p>
      </div>
      <CrmDirectory />
    </div>
  );
}
