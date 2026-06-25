import { Studio } from "./_components/studio";

export const dynamic = "force-dynamic";

export default function VisualsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Visual studio</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Generate ready-to-post images — ads, posters, carousels, and thumbnails.
          AI renders a real PNG automatically.
        </p>
      </div>
      <Studio />
    </div>
  );
}
