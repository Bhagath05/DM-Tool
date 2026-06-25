"use client";

import { ArrowRight, type LucideIcon } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

/**
 * Phase 3.3 — Action chips.
 *
 * The product principle: every insight should lead to action. Each chip is
 * a deep-link to a studio with the form pre-filled via URL query params.
 * No new backend endpoints needed — the chips simply tell each studio
 * what to render the form with.
 *
 * Studios honour these URL params on mount:
 *   /content   ?type=social_post|reel|carousel|ad_copy  &goal=
 *   /ads       ?ad_type=meta|google_search|... &objective=  &goal=
 *   /visuals   ?visual_type=ad_creative|carousel|reel|thumbnail &platform=  &goal=
 *   /campaigns ?campaign_type=product_launch|... &goal=
 */

export type ActionChip = {
  label: string;
  href: string;
  icon?: LucideIcon;
  /** Mark one chip as the primary recommendation. Renders in solid style. */
  emphasis?: boolean;
};

export function ActionChips({
  chips,
  className,
  label,
}: {
  chips: ActionChip[];
  className?: string;
  /** Optional eyebrow label, e.g. "Take action". */
  label?: string;
}) {
  if (chips.length === 0) return null;
  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {chips.map((c, i) => {
          const Icon = c.icon;
          return (
            <Link
              key={i}
              href={c.href as never}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
                c.emphasis
                  ? "border-primary bg-primary text-primary-foreground hover:bg-primary/90"
                  : "border-input bg-background hover:bg-accent",
              )}
            >
              {Icon && <Icon className="h-3 w-3" />}
              {c.label}
              <ArrowRight className="h-3 w-3 opacity-70" />
            </Link>
          );
        })}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------
//  Chip recipe builders — keep the call sites short.
// ----------------------------------------------------------------------

const enc = (s: string) => encodeURIComponent(s);

/** Chips for an existing content piece — "make more like this" patterns. */
export function chipsForContent(opts: {
  contentType: string;
  goal: string;
  platform: string;
}): ActionChip[] {
  const { contentType, goal, platform } = opts;
  const out: ActionChip[] = [];
  // Variation in the same format.
  out.push({
    label: "Make a variation",
    href: `/content?type=${enc(contentType)}&goal=${enc(goal)}&platform=${enc(platform)}`,
    emphasis: true,
  });
  // Repurpose into another format the studio supports.
  if (contentType !== "reel") {
    out.push({
      label: "Turn into a reel",
      href: `/content?type=reel&goal=${enc(goal)}&platform=${enc(platform)}`,
    });
  }
  if (contentType !== "carousel") {
    out.push({
      label: "Turn into a carousel",
      href: `/content?type=carousel&goal=${enc(goal)}&platform=${enc(platform)}`,
    });
  }
  // Cross-studio: promote into an ad.
  out.push({
    label: "Turn into an ad",
    href: `/ads?goal=${enc(goal)}`,
  });
  return out;
}

/** Chips for an existing ad. */
export function chipsForAd(opts: {
  adType: string;
  goal: string;
  objective: string;
}): ActionChip[] {
  const { adType, goal, objective } = opts;
  return [
    {
      label: "Make a variation",
      href: `/ads?ad_type=${enc(adType)}&objective=${enc(objective)}&goal=${enc(goal)}`,
      emphasis: true,
    },
    {
      label: "Design the creative",
      href: `/visuals?visual_type=ad_creative&goal=${enc(goal)}`,
    },
    {
      label: "Write a matching post",
      href: `/content?type=social_post&goal=${enc(goal)}`,
    },
  ];
}

/** Chips for a visual brief. */
export function chipsForVisual(opts: {
  visualType: string;
  goal: string;
  platform: string;
}): ActionChip[] {
  const { visualType, goal, platform } = opts;
  const out: ActionChip[] = [
    {
      label: "Make a variation",
      href: `/visuals?visual_type=${enc(visualType)}&goal=${enc(goal)}&platform=${enc(platform)}`,
      emphasis: true,
    },
    {
      label: "Write the ad copy",
      href: `/ads?goal=${enc(goal)}`,
    },
  ];
  if (visualType !== "reel") {
    out.push({
      label: "Storyboard a reel",
      href: `/visuals?visual_type=reel&goal=${enc(goal)}&platform=${enc(platform)}`,
    });
  }
  return out;
}

/** Chips for a top-converting asset row in analytics. */
export function chipsForTopAsset(opts: {
  assetType: "content" | "ad" | "visual" | "campaign";
  subtype: string;
  platform: string | null;
  goal: string;
}): ActionChip[] {
  const { assetType, subtype, platform, goal } = opts;
  const platformParam = platform ? `&platform=${enc(platform)}` : "";
  switch (assetType) {
    case "content":
      return [
        {
          label: "Clone the playbook",
          href: `/content?type=${enc(subtype)}&goal=${enc(goal)}${platformParam}`,
          emphasis: true,
        },
        {
          label: "Turn into an ad",
          href: `/ads?goal=${enc(goal)}`,
        },
      ];
    case "ad":
      return [
        {
          label: "Make a variation",
          href: `/ads?ad_type=${enc(subtype)}&goal=${enc(goal)}`,
          emphasis: true,
        },
        {
          label: "Design the creative",
          href: `/visuals?visual_type=ad_creative&goal=${enc(goal)}`,
        },
      ];
    case "visual":
      return [
        {
          label: "Clone the playbook",
          href: `/visuals?visual_type=${enc(subtype)}&goal=${enc(goal)}${platformParam}`,
          emphasis: true,
        },
      ];
    case "campaign":
      return [
        {
          label: "Plan a similar campaign",
          href: `/campaigns?campaign_type=${enc(subtype)}&goal=${enc(goal)}`,
          emphasis: true,
        },
        {
          label: "Build a bundle",
          href: `/bundles`,
        },
      ];
  }
}
