"use client";

/**
 * Phase 6.4 — the Create hub.  (Phase 6.6: on the shared page frame.)
 *
 * Creative Studio (/studio) is the ONE canonical home for creative work. The
 * full outcome-driven Studio is flag-gated (NEXT_PUBLIC_STUDIO_ENABLED); until
 * it's on, /studio shows this hub so Create is never a dead end and every real
 * generator has an obvious home. It only LINKS to existing routes — no new
 * functionality, no generators moved. Presentation uses existing tokens/
 * primitives; status/labels are text (not color alone).
 */

import {
  FileText,
  Image as ImageIcon,
  Layers,
  Linkedin,
  Megaphone,
  Send,
  SquareStack,
} from "lucide-react";
import Link from "next/link";

import { ContentGrid, PageHeader, PageShell } from "@/components/ui/page-shell";
import { Surface } from "@/components/ui/surface";

type Capability = {
  href: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
};

// Each href is a real, canonical route (verified against the App Router).
const CAPABILITIES: Capability[] = [
  { href: "/content", label: "Content studio", description: "Posts, captions and long-form — grounded in your business profile.", icon: FileText },
  { href: "/visuals", label: "Visual studio", description: "Ready-to-post images: posters, carousels and thumbnails.", icon: ImageIcon },
  { href: "/ads", label: "Ad studio", description: "Paid-media-ready ads with the reasoning behind each one.", icon: Megaphone },
  { href: "/create/linkedin", label: "LinkedIn studio", description: "A branded announcement poster plus a ready-to-post caption.", icon: Linkedin },
  { href: "/bundles", label: "Campaign bundles", description: "One click → a coordinated plan, posts, an ad and a visual brief.", icon: Layers },
  { href: "/landing-pages", label: "Lead pages", description: "Conversion-focused pages with a public URL to share anywhere.", icon: SquareStack },
  { href: "/publishing", label: "Publishing", description: "Review, approve, schedule and publish across connected platforms.", icon: Send },
];

export function CreateHub() {
  return (
    <PageShell data-testid="create-hub">
      <PageHeader
        title="Create"
        description="Everything your business needs to make for marketing, in one place. Pick what you want to create — each studio explains the strategy behind what it generates."
      />
      <ContentGrid cols={3}>
        {CAPABILITIES.map((c) => {
          const Icon = c.icon;
          return (
            <Link
              key={c.href}
              href={c.href as never}
              className="group rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Surface state="hover" padding="compact" className="h-full">
                <div className="flex items-center gap-2.5">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-ai-soft text-ai-soft-foreground transition-colors group-hover:bg-ai group-hover:text-ai-foreground" aria-hidden>
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="text-sm font-semibold text-foreground">{c.label}</span>
                </div>
                <p className="mt-2.5 text-xs leading-relaxed text-muted-foreground">{c.description}</p>
              </Surface>
            </Link>
          );
        })}
      </ContentGrid>
    </PageShell>
  );
}
