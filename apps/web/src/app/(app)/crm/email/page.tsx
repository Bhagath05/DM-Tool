import { EmailStudio } from "./_components/email-studio";

export const dynamic = "force-dynamic";

export default function CrmEmailPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Email</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Reusable templates, multi-step sequences, and open/click/reply tracking —
          all logged to your CRM timeline.
        </p>
      </div>
      <EmailStudio />
    </div>
  );
}
