import { Library } from "./_components/library";

export const dynamic = "force-dynamic";

export default function LibraryPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Everything you&apos;ve made
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          One timeline for every post, ad, reel, image, landing page, and
          bundle the platform has generated for you. Filter by type, click any
          card to jump back to the studio it came from.
        </p>
      </div>
      <Library />
    </div>
  );
}
