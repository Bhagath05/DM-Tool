import { Studio } from "./_components/studio";

export const dynamic = "force-dynamic";

export default function ContentPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Content studio
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Generate platform-native content grounded in your business profile
          and the latest trend report. Every piece comes with a strategist
          explanation of why it works.
        </p>
      </div>
      <Studio />
    </div>
  );
}
