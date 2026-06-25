import { Studio } from "./_components/studio";

export const dynamic = "force-dynamic";

export default function AdsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Ad studio</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Generate paid-media-ready ads with targeting suggestions and the
          strategic reasoning behind every piece.
        </p>
      </div>
      <Studio />
    </div>
  );
}
