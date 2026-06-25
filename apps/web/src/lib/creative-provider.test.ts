/**
 * Phase 10.5 — CreativeProvider abstraction tests.
 *
 * Three things to pin:
 *   1. `buildVisualPayload` maps each CreativeFormat to the right
 *      backend VisualType + carries platform/goal/tone through.
 *   2. The OpenAIImages adapter calls `api.visuals.generate` exactly
 *      once and normalises the response into a CreativeResult.
 *   3. The registry resolves default vs persisted provider, and
 *      tolerates stale persisted names without crashing.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "./api";
import {
  __registerProviderForTests,
  __resetCreativeProviderForTests,
  buildVisualPayload,
  getCreativeProvider,
  listCreativeProviders,
  OpenAIImagesProvider,
  setCreativeProvider,
  type CreativeBrief,
  type CreativeResult,
} from "./creative-provider";


function makeBrief(over: Partial<CreativeBrief> = {}): CreativeBrief {
  return {
    product_name: "AI Payroll Audit",
    audience: "Indian SaaS founders",
    aspect_ratio: "1:1",
    platform: "instagram",
    goal: "Generate qualified leads",
    tone: "confident",
    ...over,
  };
}


describe("buildVisualPayload", () => {
  it("maps poster → thumbnail visual_type", () => {
    const p = buildVisualPayload(makeBrief(), "poster");
    expect(p.visual_type).toBe("thumbnail");
  });

  it("maps ad_creative → ad_creative visual_type", () => {
    const p = buildVisualPayload(makeBrief(), "ad_creative");
    expect(p.visual_type).toBe("ad_creative");
  });

  it("maps social_graphic → carousel visual_type", () => {
    const p = buildVisualPayload(makeBrief(), "social_graphic");
    expect(p.visual_type).toBe("carousel");
  });

  it("forwards platform / goal / tone / landing_page_id verbatim", () => {
    const p = buildVisualPayload(
      makeBrief({
        platform: "linkedin",
        goal: "Drive demo bookings",
        tone: "professional",
        landing_page_id: "lp-123",
      }),
      "poster",
    );
    expect(p.platform).toBe("linkedin");
    expect(p.goal).toBe("Drive demo bookings");
    expect(p.tone).toBe("professional");
    expect(p.landing_page_id).toBe("lp-123");
  });
});


describe("OpenAIImagesProvider", () => {
  let generateSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    generateSpy = vi.spyOn(api.api.visuals, "generate").mockResolvedValue({
      id: "v-1",
      user_id: "u",
      business_profile_id: "bp",
      trend_report_id: null,
      landing_page_id: null,
      visual_type: "ad_creative",
      platform: "instagram",
      goal: "Generate leads",
      tone: "confident",
      strategy: {
        visual_concept: "x",
        emotional_trigger: "x",
        audience_angle: "x",
        trend_influence: "x",
        composition_principle: "x",
        conversion_rationale: "x",
      },
      output: { image_url: "https://cdn.example/asset.png" },
      share_url: null,
      is_saved: false,
      created_at: "2026-06-09T00:00:00Z",
      updated_at: "2026-06-09T00:00:00Z",
    });
  });

  afterEach(() => {
    generateSpy.mockRestore();
  });

  it("calls api.visuals.generate exactly once per generate call", async () => {
    const p = new OpenAIImagesProvider();
    await p.generateAdCreative(makeBrief());
    expect(generateSpy).toHaveBeenCalledTimes(1);
  });

  it("normalises the response into a CreativeResult", async () => {
    const p = new OpenAIImagesProvider();
    const r: CreativeResult = await p.generateAdCreative(makeBrief());
    expect(r.id).toBe("v-1");
    expect(r.provider).toBe("openai-images");
    expect(r.format).toBe("ad_creative");
    expect(r.asset_url).toBe("https://cdn.example/asset.png");
    expect(r.preview_url).toBe("https://cdn.example/asset.png");
    expect(r.metadata.strategy).toBeDefined();
  });

  it("falls back to output.url when image_url is absent", async () => {
    generateSpy.mockResolvedValueOnce({
      id: "v-2",
      user_id: "u",
      business_profile_id: "bp",
      trend_report_id: null,
      landing_page_id: null,
      visual_type: "thumbnail",
      platform: "instagram",
      goal: "x",
      tone: "confident",
      strategy: {
        visual_concept: "x",
        emotional_trigger: "x",
        audience_angle: "x",
        trend_influence: "x",
        composition_principle: "x",
        conversion_rationale: "x",
      },
      output: { url: "https://cdn.example/poster.png" },
      share_url: null,
      is_saved: false,
      created_at: "2026-06-09T00:00:00Z",
      updated_at: "2026-06-09T00:00:00Z",
    });
    const p = new OpenAIImagesProvider();
    const r = await p.generatePoster(makeBrief());
    expect(r.asset_url).toBe("https://cdn.example/poster.png");
  });

  it("each method passes its format through to the result", async () => {
    const p = new OpenAIImagesProvider();
    expect((await p.generatePoster(makeBrief())).format).toBe("poster");
    expect((await p.generateAdCreative(makeBrief())).format).toBe("ad_creative");
    expect((await p.generateSocialGraphic(makeBrief())).format).toBe("social_graphic");
  });

  it("provider.name is the registry key", () => {
    expect(new OpenAIImagesProvider().name).toBe("openai-images");
  });
});


describe("Registry — getCreativeProvider", () => {
  beforeEach(() => {
    __resetCreativeProviderForTests();
  });

  it("returns the default provider when nothing is persisted", () => {
    expect(getCreativeProvider().name).toBe("openai-images");
  });

  it("returns the persisted provider when its name is registered", () => {
    // Register a fake provider, persist its name, expect resolver to
    // return it.
    const fake = {
      name: "fake-pomelli",
      generatePoster: async () => ({} as CreativeResult),
      generateAdCreative: async () => ({} as CreativeResult),
      generateSocialGraphic: async () => ({} as CreativeResult),
    };
    __registerProviderForTests(fake);
    setCreativeProvider("fake-pomelli");
    expect(getCreativeProvider().name).toBe("fake-pomelli");
  });

  it("falls back to default when persisted name is unknown (stale)", () => {
    // Bypass setCreativeProvider's guard by writing to localStorage
    // directly — simulates a provider that was retired.
    window.localStorage.setItem(
      "aicmo.creative-provider.v1",
      "retired-provider",
    );
    expect(getCreativeProvider().name).toBe("openai-images");
  });
});


describe("listCreativeProviders", () => {
  it("includes openai-images by default", () => {
    expect(listCreativeProviders()).toContain("openai-images");
  });
});
