import { CrmBoard } from "./_components/crm-board";

export const dynamic = "force-dynamic";

export default function CrmPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">CRM</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your pipeline, deals, and forecast — with AI next-actions grounded in
          real CRM data.
        </p>
      </div>
      <CrmBoard />
    </div>
  );
}
