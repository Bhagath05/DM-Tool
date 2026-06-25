"use client";

/**
 * Phase 10.0 — Performance Intelligence section for the Overview page.
 *
 * Composes:
 *   - SectionHeading
 *   - PremiumUpload (collapsed once data exists)
 *   - The existing `<PerformanceEngineCard>` whose visual layer is
 *     already on the new design system (Phase 10.0d/e).
 *
 * We keep the original `<PerformanceEngineCard>` mounted because
 * Phase 9.1 / 9.1.5 tests pin its state machine. Here we just give
 * it a premium frame and the new upload affordance.
 */

import { BarChart3 } from "lucide-react";

import { PerformanceEngineCard } from "@/components/performance-engine-card";
import { SectionHeading } from "@/components/ui/section-heading";

export function PerformanceSection() {
  return (
    <section
      data-testid="performance-section"
      className="flex flex-col gap-4"
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <BarChart3 className="h-3 w-3" />
            From your data
          </span>
        }
        heading="Performance Intelligence"
        description="What your ads are telling us — winning audiences, creative patterns, offer signals, and where to put your next spend."
      />
      <PerformanceEngineCard />
    </section>
  );
}
