import { BundleStudio } from "./_components/bundle-studio";

export const dynamic = "force-dynamic";

export default function BundlesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Campaign bundles
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          One click → a coordinated set: a plan, posts, an ad, and a visual
          brief — all sharing the same theme, audience, and link. Your AI
          marketing team, in 15 seconds.
        </p>
      </div>
      <BundleStudio />
    </div>
  );
}
