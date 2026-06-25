import { SocialIntelligence } from "./_components/social-intelligence";

export const dynamic = "force-dynamic";

export default function SocialPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          What actually works on social
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Connect your platforms — or paste in performance data — and the AI
          extracts the patterns behind your best posts. Every reel, ad, and
          campaign generated after this inherits those patterns automatically.
        </p>
      </div>
      <SocialIntelligence />
    </div>
  );
}
