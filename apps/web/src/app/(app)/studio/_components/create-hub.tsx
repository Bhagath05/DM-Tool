"use client";

/**
 * Phase 6.4 — the Create hub.
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
    <section data-testid="create-hub" className="mx-auto max-w-5xl p-6">
      <header className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight">Create</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Everything your business needs to make for marketing, in one place.
          Pick what you want to create — each studio explains the strategy behind
          what it generates.
        </p>
      </header>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {CAPABILITIES.map((c) => {
          const Icon = c.icon;
          return (
            <Link
              key={c.href}
              href={c.href as never}
              className="group rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Surface className="h-full p-4 transition-colors group-hover:border-ai-border">
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ai-soft text-ai-soft-foreground" aria-hidden>
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="text-sm font-semibold text-foreground">{c.label}</span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{c.description}</p>
              </Surface>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
