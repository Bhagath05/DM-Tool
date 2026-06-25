/**
 * Phase 10.0 — /performance deep-dive page.
 *
 * The Overview page surfaces the highlights; this page is the full
 * Performance Intelligence surface in one focused view. Same backend
 * (Phase 9.1 / 9.1.5), no duplication.
 */

import { Sparkles } from "lucide-react";

import { PerformanceEngineCard } from "@/components/performance-engine-card";
import { SectionHeading } from "@/components/ui/section-heading";

export const dynamic = "force-dynamic";

export default function PerformancePage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8">
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="h-3 w-3" />
            Performance Intelligence
          </span>
        }
        heading="Every signal we found in your data"
        description="The complete diagnostic surface from your latest upload — audience, creative, offer, scaling, and the winning formula. Switch to Pro view in the top bar to see sections grouped by intelligence lane."
        size="lg"
      />
      <PerformanceEngineCard />
    </div>
  );
}
