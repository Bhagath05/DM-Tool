/**
 * Phase 10.4 polish — central mapping for the `?from=` deep-link
 * convention used by Command Center / Market Intelligence CTAs.
 *
 * When a card deep-links into a studio (`/create/social-posts?from=
 * command-center-posts`), the studio doesn't know where the founder
 * came from. We tag the URL with `from=<slug>` so a single
 * <FromSourceBanner> can read it and render a "Back to {source}"
 * link at the top of the destination — no per-page wiring needed.
 *
 * Add a new slug here whenever a new CTA fires a deep-link. The UI
 * silently renders nothing for unknown slugs — better an absent
 * back link than a wrong one.
 */

export interface BackSource {
  href: string;
  label: string;
}

const SOURCES: Record<string, BackSource> = {
  // ---- Command Center sources ------------------------------------
  // The hero generic + each sub-section all map to /today/command-center
  // — the founder always wants to return to the same place.
  "command-center": {
    href: "/today/command-center",
    label: "Back to AI Command Center",
  },
  "command-center-posts": {
    href: "/today/command-center",
    label: "Back to AI Command Center",
  },
  "command-center-ads": {
    href: "/today/command-center",
    label: "Back to AI Command Center",
  },
  "command-center-reels": {
    href: "/today/command-center",
    label: "Back to AI Command Center",
  },

  // ---- Market Intelligence sources -------------------------------
  "market-intel": {
    href: "/grow/market-intelligence",
    label: "Back to Market Intelligence",
  },
  "market-intel-trends": {
    href: "/grow/market-intelligence",
    label: "Back to Market Intelligence",
  },
  "market-intel-gaps": {
    href: "/grow/market-intelligence",
    label: "Back to Market Intelligence",
  },
};

/**
 * Resolve a `?from=` slug to its BackSource. Returns null when the
 * slug is missing or unrecognised — caller treats null as "render
 * nothing" rather than guessing.
 *
 * Exported for unit tests; the live consumer is `<FromSourceBanner>`.
 */
export function resolveBackSource(
  slug: string | null | undefined,
): BackSource | null {
  if (!slug) return null;
  return SOURCES[slug] ?? null;
}

/** All registered slugs — useful for tests/debug. */
export function knownBackSourceSlugs(): string[] {
  return Object.keys(SOURCES);
}
