/**
 * Phase 10.5 — CreativeProvider abstraction (Pomelli prep).
 *
 * Visual creative generation is currently powered by OpenAI Images via
 * `api.visuals.generate` (Phase 4-A backend provider abstraction). This
 * module wraps that call in a frontend-side `CreativeProvider`
 * interface so future providers — primarily Google's Pomelli once it
 * has a stable API — can drop in without touching studio code.
 *
 * Three creative formats the interface knows about:
 *
 *   - poster          → static portrait/landscape image with copy overlay
 *   - ad_creative     → ad-platform-ready creative (1:1 or 9:16)
 *   - social_graphic  → social-platform-ready image (1:1 or 4:5)
 *
 * Each maps to a `VisualType` preset on the existing backend endpoint.
 * Backend stays untouched — the abstraction is purely a frontend
 * adapter pattern.
 *
 * Constraint: NO vendor lock-in. Adding Pomelli later is a 30-line file
 * (implement the same 3 methods, register in `provider-registry.ts`).
 * Switching providers is one localStorage flip via `use-creative-provider`.
 */

import { api, type GenerateVisualPayload, type VisualType } from "./api";

// ---------------------------------------------------------------------
//  Public types
// ---------------------------------------------------------------------

export type CreativeAspect = "1:1" | "4:5" | "9:16" | "16:9";
export type CreativeFormat = "poster" | "ad_creative" | "social_graphic";

/**
 * Inputs for any creative generation call. Backend providers may use a
 * subset; the interface accepts the full superset so future providers
 * can use richer briefs without changing studio code.
 */
export interface CreativeBrief {
  product_name: string;
  audience: string;
  /** Optional offer or promo hook ("20% off first audit"). */
  offer?: string | null;
  /** Optional brand palette hint — when provided, providers should honour it. */
  brand_palette?: { primary: string; secondary?: string };
  aspect_ratio: CreativeAspect;
  /** Optional copy overlay text (e.g. headline burned into the image). */
  copy_overlay?: string;
  /** Platform hint passes through to the backend prompt. */
  platform: string;
  /** Founder-friendly goal label — used by the prompt and AssetFooter. */
  goal: string;
  /** Optional brand tone. Defaults to "confident" if absent. */
  tone?: string;
  /** Optional landing-page linkage for context-aware prompts. */
  landing_page_id?: string;
}

/** Normalised output every provider must produce. */
export interface CreativeResult {
  id: string;
  /** URL to the rendered asset (signed/CDN). */
  asset_url: string;
  /** Lower-resolution preview URL. May equal asset_url if no preview tier. */
  preview_url: string;
  /** Which provider produced this asset — useful for analytics. */
  provider: string;
  /** Which format slot the asset is for. */
  format: CreativeFormat;
  /** Anything provider-specific that doesn't fit the normalised shape. */
  metadata: Record<string, unknown>;
}

/**
 * The contract every provider implements. A studio only ever depends
 * on this interface — never on a concrete provider class.
 */
export interface CreativeProvider {
  readonly name: string;
  generatePoster(brief: CreativeBrief): Promise<CreativeResult>;
  generateAdCreative(brief: CreativeBrief): Promise<CreativeResult>;
  generateSocialGraphic(brief: CreativeBrief): Promise<CreativeResult>;
}

// ---------------------------------------------------------------------
//  Default adapter — wraps api.visuals.generate
// ---------------------------------------------------------------------

/**
 * Maps a frontend `CreativeFormat` to the backend's `VisualType` enum.
 * Kept tight — when the backend grows a new visual_type, add the row
 * here rather than littering studio code with conditionals.
 */
const FORMAT_TO_VISUAL_TYPE: Record<CreativeFormat, VisualType> = {
  poster: "thumbnail",        // closest existing slot for static posters
  ad_creative: "ad_creative",
  social_graphic: "carousel", // single-slide social graphic uses carousel preset
};

/**
 * Build the existing-API payload from a CreativeBrief.
 * Exported for tests (and for any future provider that wants to
 * forward to the same backend).
 */
export function buildVisualPayload(
  brief: CreativeBrief,
  format: CreativeFormat,
): GenerateVisualPayload {
  return {
    visual_type: FORMAT_TO_VISUAL_TYPE[format],
    platform: brief.platform,
    goal: brief.goal,
    tone: brief.tone,
    landing_page_id: brief.landing_page_id,
  };
}

export class OpenAIImagesProvider implements CreativeProvider {
  readonly name = "openai-images";

  async generatePoster(brief: CreativeBrief): Promise<CreativeResult> {
    return this.#generate(brief, "poster");
  }

  async generateAdCreative(brief: CreativeBrief): Promise<CreativeResult> {
    return this.#generate(brief, "ad_creative");
  }

  async generateSocialGraphic(brief: CreativeBrief): Promise<CreativeResult> {
    return this.#generate(brief, "social_graphic");
  }

  /**
   * Single private worker — both ergonomics (no triple-duplicate body)
   * and so subclasses can override one place if a future provider
   * needs to special-case one format.
   */
  async #generate(
    brief: CreativeBrief,
    format: CreativeFormat,
  ): Promise<CreativeResult> {
    const payload = buildVisualPayload(brief, format);
    const visual = await api.visuals.generate(payload);
    const assetUrl = String(
      (visual.output?.image_url as string | undefined) ??
        (visual.output?.url as string | undefined) ??
        "",
    );
    return {
      id: visual.id,
      asset_url: assetUrl,
      preview_url: assetUrl,
      provider: this.name,
      format,
      metadata: {
        strategy: visual.strategy,
        visual_type: visual.visual_type,
        is_saved: visual.is_saved,
      },
    };
  }
}

// ---------------------------------------------------------------------
//  Registry — pluggable, swap-friendly
// ---------------------------------------------------------------------

const REGISTRY: Record<string, CreativeProvider> = {
  "openai-images": new OpenAIImagesProvider(),
  // Future:
  // "pomelli": new PomelliProvider(),
};

const DEFAULT_PROVIDER_NAME = "openai-images";
const STORAGE_KEY = "aicmo.creative-provider.v1";

/**
 * Resolve the active provider — checks localStorage for a per-device
 * override, falls back to the default. Returns the default if the
 * persisted name no longer exists in the registry (e.g. a provider
 * was retired).
 */
export function getCreativeProvider(): CreativeProvider {
  if (typeof window !== "undefined") {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored && REGISTRY[stored]) return REGISTRY[stored];
    } catch {
      /* ignore — fall through to default */
    }
  }
  return REGISTRY[DEFAULT_PROVIDER_NAME];
}

/**
 * Set the active provider for this device. No-op if `name` isn't
 * registered — silent rather than throwing so a stale persisted value
 * never crashes a studio.
 */
export function setCreativeProvider(name: string): void {
  if (typeof window === "undefined") return;
  if (!REGISTRY[name]) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, name);
  } catch {
    /* persistence is best-effort */
  }
}

/** List every registered provider name — useful for settings UI. */
export function listCreativeProviders(): string[] {
  return Object.keys(REGISTRY);
}

// Test-only.
export function __registerProviderForTests(provider: CreativeProvider): void {
  REGISTRY[provider.name] = provider;
}

export function __resetCreativeProviderForTests(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
