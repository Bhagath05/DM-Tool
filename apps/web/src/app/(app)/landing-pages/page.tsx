import { LandingPagesList } from "./_components/list";

export const dynamic = "force-dynamic";

export default function LandingPagesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Lead pages</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Conversion-focused pages where the leads come in. Each page is a
          public URL — share it from any campaign, ad or post.
        </p>
      </div>
      <LandingPagesList />
    </div>
  );
}
