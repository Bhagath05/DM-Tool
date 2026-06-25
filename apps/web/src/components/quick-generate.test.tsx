/**
 * Phase 8 — QuickGenerate tests.
 *
 * Pins the "Today → Generate → Result" contract:
 *
 *  1. Clicking the button opens the modal and auto-fires
 *     `api.content.generate(...)` on mount.
 *  2. The modal renders the Constitution surface (confidence band +
 *     reason + expected result) **above** the generated content.
 *  3. The result panel surfaces the founder-friendly fields
 *     (HOOK, body/script, CAPTION, HASHTAGS, CTA) by delegating to
 *     `ContentRenderer`.
 *  4. The "Generate another" button re-fires the generate call.
 *  5. Transient errors surface a retry + a "customize first" escape
 *     hatch deep-linking back to the studio with the original params.
 *  6. A 409 (no profile) surfaces an onboarding nudge.
 *  7. The platform resolver pulls the founder's first preferred
 *     platform when the caller passes `null`, falling back to
 *     "Instagram" if the profile is unavailable.
 *  8. The context builders (`quickGenerateFromOpportunity`,
 *     `quickGenerateFromTrend`) honour the Constitution gate:
 *       - ad opportunities → null
 *       - unsupported content formats (e.g. blog_outline) → null
 *       - legacy trends without advisory fields → null
 */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  type GeneratedContent,
  type Opportunity,
  type TrendingTopic,
} from "@/lib/api";

const generateMock = vi.fn();
const businessGetMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      content: { generate: (...args: unknown[]) => generateMock(...args) },
      business: { get: () => businessGetMock() },
    },
  };
});

import {
  QuickGenerateButton,
  QuickGenerateModal,
  buildCustomizeHref,
  quickGenerateFromOpportunity,
  quickGenerateFromTrend,
  type QuickGenerateContext,
} from "./quick-generate";

// ----------------------------------------------------------------------
//  Fixtures
// ----------------------------------------------------------------------

const SOCIAL_RESULT: GeneratedContent = {
  id: "gen-1",
  user_id: "u-1",
  business_profile_id: "bp-1",
  trend_report_id: null,
  landing_page_id: null,
  content_type: "social_post",
  platform: "Instagram",
  goal: "Build brand awareness",
  tone: "warm",
  strategy: {
    trend_influence: "rising",
    audience_angle: "small-business founders",
    strategy_note: "lead with the result",
  },
  output: {
    hook: "Most coffee shops lose customers to one fixable mistake.",
    body: "Here's the 3-step fix that saved us 18% of repeat visits last month.",
    hashtags: ["coffee", "smallbusiness", "barista"],
    cta: "Try it for one week and DM us your numbers.",
  },
  share_url: null,
  is_saved: false,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const REEL_RESULT: GeneratedContent = {
  ...SOCIAL_RESULT,
  id: "gen-2",
  content_type: "reel",
  output: {
    hook: "Here's the 30-second test we run every morning.",
    beats: [
      { label: "Smell", description: "Open the bag, smell the beans." },
      { label: "Crush", description: "Pinch one to check the oils." },
      { label: "Brew", description: "Pull a 1:2 shot in 28 seconds." },
    ],
    on_screen_text: ["Step 1 — Smell", "Step 2 — Crush", "Step 3 — Brew"],
    caption:
      "We taste-test every shipment before it touches a customer's cup.",
    hashtags: ["#coffee", "#barista"],
    cta: "Save this for your next bean delivery.",
  },
};

const CONTENT_CONTEXT: QuickGenerateContext = {
  request: {
    content_type: "social_post",
    platform: "Instagram",
    goal: "Build brand awareness",
  },
  source: {
    label: "Opportunity · Leads",
    headline: "People are asking about pricing",
    reason: "Pricing search volume up 22% and 3 lead messages mention price.",
    expectedResult: "10-20 qualified leads over the next month.",
    confidence: 78,
  },
};

const CONTENT_OPP: Opportunity = {
  id: "00000000-0000-0000-0000-00000000c001",
  kind: "content",
  headline: "People are asking about pricing",
  what_is_happening: "3 of 8 recent lead messages mention price.",
  why_it_matters: "Pricing confusion kills warm leads.",
  recommended_action: "Post a pricing comparison reel.",
  expected_result: "10-20 qualified leads next month.",
  confidence: 78,
  reason: "Pricing search volume +22%.",
  impact_category: "lead",
  evidence: ["Top channel: Instagram"],
  generator: {
    target: "content",
    format: "reel",
    platform: "Instagram",
    goal: "Build brand awareness",
    objective: null,
  },
};

const AD_OPP: Opportunity = {
  ...CONTENT_OPP,
  id: "00000000-0000-0000-0000-00000000a001",
  kind: "ad",
  generator: {
    target: "ad",
    format: "meta",
    platform: null,
    goal: "Drive sales",
    objective: "leads",
  },
};

const ADVISORY_TREND: TrendingTopic = {
  topic: "Specialty coffee guides",
  why_it_matters: "Espresso questions on Reddit are climbing.",
  suggested_angles: ["Bean-by-bean walkthrough"],
  relevance_score: 78,
  recommended_action:
    "Post an Instagram reel walking through your espresso bean selection.",
  expected_result: "80-150 extra people see it; 1-3 walk in this week.",
  confidence: 78,
  reason: "'Espresso bean comparison' rising +45% on Google Trends.",
};

const LEGACY_TREND: TrendingTopic = {
  topic: "Cold brew season",
  why_it_matters: "Local search for cold brew jumped 18%.",
  suggested_angles: ["Cold brew tasting note"],
  relevance_score: 65,
  recommended_action: null,
  expected_result: null,
  confidence: null,
  reason: null,
};

// ----------------------------------------------------------------------
//  Setup
// ----------------------------------------------------------------------

beforeEach(() => {
  generateMock.mockReset();
  businessGetMock.mockReset();
  // Default profile lookup — caller overrides per test when needed.
  businessGetMock.mockResolvedValue({
    id: "bp-1",
    user_id: "u-1",
    business_name: "Acme Roasters",
    industry: "Coffee",
    target_audience: "Small business owners",
    brand_tone: "warm",
    location: null,
    goals: ["brand_awareness"],
    preferred_platforms: ["LinkedIn", "Instagram"],
    additional_context: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
});

afterEach(() => {
  generateMock.mockReset();
  businessGetMock.mockReset();
});

// ----------------------------------------------------------------------
//  Pure context builders
// ----------------------------------------------------------------------

describe("quickGenerateFromOpportunity", () => {
  it("returns a context for content opportunities with supported formats", () => {
    const ctx = quickGenerateFromOpportunity(CONTENT_OPP);
    expect(ctx).not.toBeNull();
    expect(ctx?.request.content_type).toBe("reel");
    expect(ctx?.request.platform).toBe("Instagram");
    expect(ctx?.source.confidence).toBe(78);
    expect(ctx?.source.headline).toMatch(/pricing/i);
  });

  it("returns null for AD opportunities — those live in the /ads studio", () => {
    expect(quickGenerateFromOpportunity(AD_OPP)).toBeNull();
  });

  it("coerces short_video_script to reel so the content backend accepts it", () => {
    const opp: Opportunity = {
      ...CONTENT_OPP,
      generator: { ...CONTENT_OPP.generator, format: "short_video_script" },
    };
    expect(quickGenerateFromOpportunity(opp)?.request.content_type).toBe(
      "reel",
    );
  });

  it("returns null when the format is unsupported (e.g. blog_outline)", () => {
    const opp: Opportunity = {
      ...CONTENT_OPP,
      generator: { ...CONTENT_OPP.generator, format: "blog_outline" },
    };
    expect(quickGenerateFromOpportunity(opp)).toBeNull();
  });
});

describe("quickGenerateFromTrend", () => {
  it("returns a context for advisory trends with all four fields populated", () => {
    const ctx = quickGenerateFromTrend(ADVISORY_TREND);
    expect(ctx).not.toBeNull();
    expect(ctx?.request.content_type).toBe("social_post");
    expect(ctx?.request.platform).toBeNull();
    expect(ctx?.request.goal).toBe(ADVISORY_TREND.recommended_action);
    expect(ctx?.source.confidence).toBe(78);
    expect(ctx?.source.headline).toMatch(/specialty coffee guides/i);
  });

  it("returns null when the trend is missing advisory fields (legacy report)", () => {
    expect(quickGenerateFromTrend(LEGACY_TREND)).toBeNull();
  });
});

describe("buildCustomizeHref", () => {
  it("uses the result's platform when present", () => {
    expect(buildCustomizeHref(CONTENT_CONTEXT, SOCIAL_RESULT)).toBe(
      "/content?type=social_post&platform=Instagram&goal=Build+brand+awareness",
    );
  });

  it("falls back to the request platform when no result yet", () => {
    expect(buildCustomizeHref(CONTENT_CONTEXT, null)).toBe(
      "/content?type=social_post&platform=Instagram&goal=Build+brand+awareness",
    );
  });

  it("omits platform entirely when both result + request are null", () => {
    const ctx: QuickGenerateContext = {
      ...CONTENT_CONTEXT,
      request: { ...CONTENT_CONTEXT.request, platform: null },
    };
    expect(buildCustomizeHref(ctx, null)).toBe(
      "/content?type=social_post&goal=Build+brand+awareness",
    );
  });
});

// ----------------------------------------------------------------------
//  Button → modal lifecycle
// ----------------------------------------------------------------------

describe("QuickGenerateButton — modal lifecycle", () => {
  it("does not auto-fire generate before the button is clicked", async () => {
    render(<QuickGenerateButton context={CONTENT_CONTEXT} />);
    expect(generateMock).not.toHaveBeenCalled();
    expect(screen.queryByTestId("quick-generate-modal")).toBeNull();
  });

  it("opens the modal and fires generate on click", async () => {
    generateMock.mockResolvedValue(SOCIAL_RESULT);
    render(<QuickGenerateButton context={CONTENT_CONTEXT} />);

    fireEvent.click(screen.getByTestId("quick-generate-button"));

    await waitFor(() => {
      expect(generateMock).toHaveBeenCalledTimes(1);
    });
    expect(generateMock).toHaveBeenCalledWith({
      content_type: "social_post",
      platform: "Instagram",
      goal: "Build brand awareness",
      tone: undefined,
    });
    expect(screen.getByTestId("quick-generate-modal")).toBeInTheDocument();
  });

  it("renders the Constitution context strip above the generation", async () => {
    generateMock.mockReturnValue(new Promise(() => {})); // pending
    render(<QuickGenerateButton context={CONTENT_CONTEXT} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    const strip = await screen.findByTestId("quick-generate-context");
    expect(strip).toHaveTextContent(
      /pricing search volume up 22%/i,
    );
    expect(strip).toHaveTextContent(/10-20 qualified leads/i);
    expect(
      screen.getByTestId("quick-generate-confidence"),
    ).toHaveTextContent(/78%/);
    // 78 is in the medium tier (60-79 in our local band map).
    expect(
      screen.getByTestId("quick-generate-confidence"),
    ).toHaveTextContent(/medium confidence/i);
  });

  it("shows the loading panel while generation is in-flight", async () => {
    generateMock.mockReturnValue(new Promise(() => {}));
    render(<QuickGenerateButton context={CONTENT_CONTEXT} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    expect(
      await screen.findByTestId("quick-generate-loading"),
    ).toBeInTheDocument();
    expect(screen.getByText(/drafting your post/i)).toBeInTheDocument();
  });
});

// ----------------------------------------------------------------------
//  Result panel
// ----------------------------------------------------------------------

describe("QuickGenerateButton — result", () => {
  it("renders HOOK / BODY / CTA / HASHTAGS for a social post", async () => {
    generateMock.mockResolvedValue(SOCIAL_RESULT);
    render(<QuickGenerateButton context={CONTENT_CONTEXT} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    await screen.findByTestId("quick-generate-result");

    expect(screen.getByText(/most coffee shops lose/i)).toBeInTheDocument();
    expect(screen.getByText(/3-step fix that saved us/i)).toBeInTheDocument();
    expect(screen.getByText(/try it for one week/i)).toBeInTheDocument();
    expect(screen.getByText("#coffee")).toBeInTheDocument();
    expect(screen.getByText("#smallbusiness")).toBeInTheDocument();
  });

  it("renders the HOOK + SCRIPT (beats) + CAPTION + CTA for a reel", async () => {
    generateMock.mockResolvedValue(REEL_RESULT);
    const reelContext: QuickGenerateContext = {
      ...CONTENT_CONTEXT,
      request: { ...CONTENT_CONTEXT.request, content_type: "reel" },
    };
    render(<QuickGenerateButton context={reelContext} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    await screen.findByTestId("quick-generate-result");

    expect(screen.getByText(/30-second test we run/i)).toBeInTheDocument();
    expect(screen.getByText(/smell the beans/i)).toBeInTheDocument();
    expect(screen.getByText(/we taste-test every shipment/i)).toBeInTheDocument();
    expect(screen.getByText(/save this for your next bean delivery/i)).toBeInTheDocument();
  });

  it("exposes a Customize-in-studio deep-link with the request params", async () => {
    generateMock.mockResolvedValue(SOCIAL_RESULT);
    render(<QuickGenerateButton context={CONTENT_CONTEXT} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    const link = (await screen.findByTestId(
      "quick-generate-customize",
    )) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(
      "/content?type=social_post&platform=Instagram&goal=Build+brand+awareness",
    );
  });

  it("regenerates when the user clicks Generate another", async () => {
    generateMock
      .mockResolvedValueOnce(SOCIAL_RESULT)
      .mockResolvedValueOnce({ ...SOCIAL_RESULT, id: "gen-1b" });

    render(<QuickGenerateButton context={CONTENT_CONTEXT} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    await screen.findByTestId("quick-generate-result");
    expect(generateMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("quick-generate-regenerate"));

    await waitFor(() => {
      expect(generateMock).toHaveBeenCalledTimes(2);
    });
  });

  it("closes the modal when the user clicks Done", async () => {
    generateMock.mockResolvedValue(SOCIAL_RESULT);
    render(<QuickGenerateButton context={CONTENT_CONTEXT} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    await screen.findByTestId("quick-generate-result");
    fireEvent.click(screen.getByTestId("quick-generate-done"));

    await waitFor(() => {
      expect(screen.queryByTestId("quick-generate-modal")).toBeNull();
    });
  });
});

// ----------------------------------------------------------------------
//  Platform resolution
// ----------------------------------------------------------------------

describe("QuickGenerateButton — platform resolution", () => {
  it("uses the founder's first preferred platform when context.platform is null", async () => {
    generateMock.mockResolvedValue(SOCIAL_RESULT);
    const ctx: QuickGenerateContext = {
      ...CONTENT_CONTEXT,
      request: { ...CONTENT_CONTEXT.request, platform: null },
    };
    render(<QuickGenerateButton context={ctx} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    await waitFor(() => expect(generateMock).toHaveBeenCalled());
    expect(generateMock).toHaveBeenCalledWith(
      expect.objectContaining({ platform: "LinkedIn" }),
    );
  });

  it("falls back to Instagram when the profile lookup fails", async () => {
    businessGetMock.mockRejectedValue(new Error("network"));
    generateMock.mockResolvedValue(SOCIAL_RESULT);
    const ctx: QuickGenerateContext = {
      ...CONTENT_CONTEXT,
      request: { ...CONTENT_CONTEXT.request, platform: null },
    };
    render(<QuickGenerateButton context={ctx} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    await waitFor(() => expect(generateMock).toHaveBeenCalled());
    expect(generateMock).toHaveBeenCalledWith(
      expect.objectContaining({ platform: "Instagram" }),
    );
  });
});

// ----------------------------------------------------------------------
//  Error states
// ----------------------------------------------------------------------

describe("QuickGenerateButton — error states", () => {
  it("surfaces a friendly retry panel on transient failures", async () => {
    generateMock.mockRejectedValueOnce(new Error("503 unavailable"));
    render(<QuickGenerateButton context={CONTENT_CONTEXT} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    expect(
      await screen.findByTestId("quick-generate-error"),
    ).toBeInTheDocument();
    expect(screen.getByText(/heavy load/i)).toBeInTheDocument();

    // Retry button re-fires generate.
    generateMock.mockResolvedValueOnce(SOCIAL_RESULT);
    fireEvent.click(screen.getByTestId("quick-generate-error-retry"));
    await screen.findByTestId("quick-generate-result");
    expect(generateMock).toHaveBeenCalledTimes(2);
  });

  it("error panel exposes a Customize-in-studio escape hatch", async () => {
    generateMock.mockRejectedValueOnce(new Error("kaboom"));
    render(<QuickGenerateButton context={CONTENT_CONTEXT} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    const link = (await screen.findByTestId(
      "quick-generate-error-customize",
    )) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(
      "/content?type=social_post&platform=Instagram&goal=Build+brand+awareness",
    );
  });

  it("surfaces the onboarding nudge on a 409 (no profile)", async () => {
    generateMock.mockRejectedValueOnce(new ApiError("no profile", 409, {}));
    render(<QuickGenerateButton context={CONTENT_CONTEXT} />);
    fireEvent.click(screen.getByTestId("quick-generate-button"));

    expect(
      await screen.findByTestId("quick-generate-no-profile"),
    ).toBeInTheDocument();
  });
});

// ----------------------------------------------------------------------
//  Headless modal (direct control)
// ----------------------------------------------------------------------

describe("QuickGenerateModal — controlled mode", () => {
  it("re-fires generate when the parent re-opens it", async () => {
    generateMock.mockResolvedValue(SOCIAL_RESULT);

    // Tiny harness that exposes its open setter via a ref so the test
    // can toggle it without rendering an extra trigger button.
    const setOpenRef: { current: ((v: boolean) => void) | null } = {
      current: null,
    };
    function Harness() {
      const [open, setOpen] = useState(false);
      setOpenRef.current = setOpen;
      return (
        <QuickGenerateModal
          open={open}
          onOpenChange={setOpen}
          context={CONTENT_CONTEXT}
        />
      );
    }

    render(<Harness />);
    expect(generateMock).not.toHaveBeenCalled();

    await act(async () => {
      setOpenRef.current?.(true);
    });
    await waitFor(() => expect(generateMock).toHaveBeenCalledTimes(1));

    // Close + reopen → fresh fire.
    await act(async () => {
      setOpenRef.current?.(false);
    });
    await act(async () => {
      setOpenRef.current?.(true);
    });
    await waitFor(() => expect(generateMock).toHaveBeenCalledTimes(2));
  });
});
