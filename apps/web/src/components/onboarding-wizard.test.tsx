/**
 * OnboardingWizard tests — A4 spec.
 *
 * Coverage:
 *   - Validation: only Business Name, Brand Name, Primary Goal block Next
 *   - Other fields don't block advancement
 *   - Slug auto-derivation happens silently in the submit payload
 *   - Back/Next preserves state
 *   - Mount preflight: skip wizard if org+brand exist
 *   - Mount preflight: resume at step 2 if org-only
 *   - Submit happy path → router.push("/dashboard")
 *   - Submit error (409) → inline message, no nav
 *   - Persistence to localStorage between steps
 */

import { StrictMode } from "react";

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const routerPush = vi.fn();
const routerReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: routerPush,
    replace: routerReplace,
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/onboarding",
  useSearchParams: () => new URLSearchParams(),
}));

// Mock api so we control /me preflight + submit per test.
const meMock = vi.fn();
const createWorkspaceMock = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      me: (opts?: unknown) => meMock(opts),
      onboarding: {
        createWorkspace: (...args: unknown[]) => createWorkspaceMock(...args),
      },
    },
  };
});

import { ApiError } from "@/lib/api";
import {
  OnboardingWizard,
  WIZARD_STORAGE_KEY,
} from "./onboarding-wizard";

const NO_MEMBERSHIPS_ME = {
  user: {
    id: "u1",
    clerk_user_id: "clerk_1",
    email: "u@example.com",
    display_name: null,
    avatar_url: null,
    status: "active",
    last_seen_at: null,
    created_at: "2026-01-01T00:00:00Z",
  },
  memberships: [],
  active: null,
  suggested_route: "/onboarding",
};

function meWithOrgAndBrand() {
  return {
    ...NO_MEMBERSHIPS_ME,
    memberships: [
      {
        organization: {
          id: "org-1",
          slug: "acme",
          name: "Acme",
          status: "active",
          member_count: 1,
          brand_count: 1,
        },
        role_slugs: ["owner"],
        permissions: ["content.create"],
        brands: [
          { id: "brand-1", slug: "main", name: "Main", status: "active" },
        ],
        last_active_brand_id: "brand-1",
        joined_at: "2026-01-01T00:00:00Z",
      },
    ],
    suggested_route: "/dashboard",
  };
}

function meWithOrgOnly() {
  return {
    ...NO_MEMBERSHIPS_ME,
    memberships: [
      {
        organization: {
          id: "org-existing",
          slug: "acme-pre",
          name: "Acme Pre-Existing",
          status: "active",
          member_count: 1,
          brand_count: 0,
        },
        role_slugs: ["owner"],
        permissions: ["content.create"],
        brands: [],
        last_active_brand_id: null,
        joined_at: "2026-01-01T00:00:00Z",
      },
    ],
    suggested_route: "/onboarding",
  };
}

beforeEach(() => {
  window.localStorage.clear();
  routerPush.mockReset();
  routerReplace.mockReset();
  meMock.mockReset();
  createWorkspaceMock.mockReset();
  // Default: fresh user with no memberships.
  meMock.mockResolvedValue(NO_MEMBERSHIPS_ME);
});

afterEach(() => {
  window.localStorage.clear();
});

// ---------------------------------------------------------------------
//  Mount preflight (skip / resume / fresh)
// ---------------------------------------------------------------------

describe("OnboardingWizard mount preflight", () => {
  it("redirects to /dashboard when user already has org + brand", async () => {
    meMock.mockResolvedValue(meWithOrgAndBrand());

    render(<OnboardingWizard />);

    await waitFor(() => {
      expect(routerReplace).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("starts at step 2 with org name pre-filled when user has org-only", async () => {
    meMock.mockResolvedValue(meWithOrgOnly());

    render(<OnboardingWizard />);

    // Should land on step 2 (brand-name field present).
    await waitFor(() => {
      expect(screen.getByTestId("field-brand-name")).toBeInTheDocument();
    });
    expect(routerReplace).not.toHaveBeenCalled();
  });

  it("starts at step 1 with empty fields when nothing exists", async () => {
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await startWizard(user);
    await waitFor(() => {
      expect(screen.getByTestId("field-business-name")).toBeInTheDocument();
    });
    expect(
      (screen.getByTestId("field-business-name") as HTMLInputElement).value,
    ).toBe("");
  });

  it("survives /me preflight failure by falling back to fresh wizard", async () => {
    meMock.mockRejectedValue(new ApiError("network down", 500, null));
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await startWizard(user);
    await waitFor(() => {
      expect(screen.getByTestId("field-business-name")).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------
//  Validation
// ---------------------------------------------------------------------

describe("OnboardingWizard validation — only 3 fields strict", () => {
  it("step 1: Next disabled until business_name is filled", async () => {
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await startWizard(user);
    await waitFor(() =>
      expect(screen.getByTestId("field-business-name")).toBeInTheDocument(),
    );

    expect(
      (screen.getByTestId("wizard-next") as HTMLButtonElement).disabled,
    ).toBe(true);

    await user.type(screen.getByTestId("field-business-name"), "Acme");
    expect(
      (screen.getByTestId("wizard-next") as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("step 1: industry + website are optional (don't block advance)", async () => {
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await startWizard(user);
    await waitFor(() =>
      expect(screen.getByTestId("field-business-name")).toBeInTheDocument(),
    );
    await user.type(screen.getByTestId("field-business-name"), "Acme");
    // industry + website blank — Next still enabled.
    expect(
      (screen.getByTestId("wizard-next") as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("step 2: brand_description + target_audience are optional", async () => {
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await startWizard(user);
    await waitFor(() =>
      expect(screen.getByTestId("field-business-name")).toBeInTheDocument(),
    );
    await user.type(screen.getByTestId("field-business-name"), "Acme");
    await user.click(screen.getByTestId("wizard-next")); // → step 2

    await user.type(screen.getByTestId("field-brand-name"), "Espresso");
    expect(
      (screen.getByTestId("wizard-next") as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("step 3: Next disabled until a primary goal is chosen", async () => {
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await advanceTo(user, 3);
    expect(
      (screen.getByTestId("wizard-next") as HTMLButtonElement).disabled,
    ).toBe(true);

    await user.click(screen.getByTestId("goal-leads"));
    expect(
      (screen.getByTestId("wizard-next") as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("step 3: platforms + tone are optional (Next not gated on them)", async () => {
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await advanceTo(user, 3);
    await user.click(screen.getByTestId("goal-leads"));
    // Platforms + tone untouched — Next still enabled.
    expect(
      (screen.getByTestId("wizard-next") as HTMLButtonElement).disabled,
    ).toBe(false);
  });
});

// ---------------------------------------------------------------------
//  Back / forward state preservation
// ---------------------------------------------------------------------

describe("OnboardingWizard back navigation", () => {
  it("preserves state when going back and forward", async () => {
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await startWizard(user);
    await waitFor(() =>
      expect(screen.getByTestId("field-business-name")).toBeInTheDocument(),
    );

    await user.type(screen.getByTestId("field-business-name"), "Acme");
    await user.type(screen.getByTestId("field-industry"), "Cafe");
    await user.click(screen.getByTestId("wizard-next")); // → 2

    await user.type(screen.getByTestId("field-brand-name"), "Espresso");
    await user.click(screen.getByTestId("wizard-back")); // → 1

    expect(
      (screen.getByTestId("field-business-name") as HTMLInputElement).value,
    ).toBe("Acme");
    expect(
      (screen.getByTestId("field-industry") as HTMLInputElement).value,
    ).toBe("Cafe");

    await user.click(screen.getByTestId("wizard-next")); // → 2
    expect(
      (screen.getByTestId("field-brand-name") as HTMLInputElement).value,
    ).toBe("Espresso");
  });
});

// ---------------------------------------------------------------------
//  Resume from localStorage
// ---------------------------------------------------------------------

describe("OnboardingWizard resume", () => {
  it("restores state from localStorage on mount", async () => {
    window.localStorage.setItem(
      WIZARD_STORAGE_KEY,
      JSON.stringify({
        step: 2,
        business_name: "Persisted Acme",
        industry: "",
        website: "",
        brand_name: "Persisted Brand",
        brand_description: "",
        target_audience: "",
        primary_goal: "",
        preferred_platforms: [],
        brand_tone: "",
      }),
    );

    render(<OnboardingWizard />);
    await waitFor(() =>
      expect(screen.getByTestId("field-brand-name")).toBeInTheDocument(),
    );
    expect(
      (screen.getByTestId("field-brand-name") as HTMLInputElement).value,
    ).toBe("Persisted Brand");
  });

  it("survives corrupt JSON in localStorage", async () => {
    window.localStorage.setItem(WIZARD_STORAGE_KEY, "{not json");
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await startWizard(user);
    await waitFor(() =>
      expect(screen.getByTestId("field-business-name")).toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------
//  Happy path submit
// ---------------------------------------------------------------------

describe("OnboardingWizard happy path", () => {
  it("submits full 3-entity payload and navigates to /dashboard", async () => {
    createWorkspaceMock.mockResolvedValue({
      organization_id: "org-uuid",
      organization_slug: "acme",
      organization_name: "Acme",
      brand_id: "brand-uuid",
      brand_slug: "espresso",
      brand_name: "Espresso",
      member_id: "mem-uuid",
      role_slugs: ["owner"],
    });

    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await fillFullForm(user);

    expect(screen.getByTestId("wizard-review")).toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByTestId("wizard-submit"));
    });

    await waitFor(() => {
      expect(createWorkspaceMock).toHaveBeenCalledTimes(1);
    });

    const payload = createWorkspaceMock.mock.calls[0][0];
    expect(payload).toMatchObject({
      organization_name: "Acme",
      organization_slug: "acme",
      brand_name: "Espresso",
      brand_slug: "espresso",
      industry: "Cafe",
      target_audience: "Young professionals buying coffee on commute",
      primary_goal: "leads",
      brand_tone: "friendly",
    });
    expect(payload.preferred_platforms).toContain("instagram");

    await waitFor(() => {
      expect(routerPush).toHaveBeenCalledWith("/dashboard");
    });

    // Persisted draft cleared on success.
    expect(window.localStorage.getItem(WIZARD_STORAGE_KEY)).toBeNull();
    // Tenant cache seeded.
    expect(
      window.localStorage.getItem("aicmo.tenant.selection.v1"),
    ).toContain("org-uuid");
  });

  it("auto-derives slugs from names (no slug fields visible)", async () => {
    createWorkspaceMock.mockResolvedValue({
      organization_id: "o",
      organization_slug: "acme-coffee-co",
      organization_name: "Acme Coffee Co.",
      brand_id: "b",
      brand_slug: "acme-espresso",
      brand_name: "Acme Espresso",
      member_id: "m",
      role_slugs: ["owner"],
    });

    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await startWizard(user);

    // Fill with names that have punctuation/spaces; slugify normalizes.
    await waitFor(() =>
      expect(screen.getByTestId("field-business-name")).toBeInTheDocument(),
    );
    await user.type(
      screen.getByTestId("field-business-name"),
      "Acme Coffee Co.",
    );
    await user.click(screen.getByTestId("wizard-next")); // → 2
    await user.type(
      screen.getByTestId("field-brand-name"),
      "Acme Espresso!",
    );
    await user.click(screen.getByTestId("wizard-next")); // → 3
    await user.click(screen.getByTestId("goal-leads"));
    await user.click(screen.getByTestId("wizard-next")); // → 4 (Persona)
    // Skip persona — optional.
    await user.click(screen.getByTestId("wizard-next")); // → 5 (Review)

    await act(async () => {
      await user.click(screen.getByTestId("wizard-submit"));
    });

    await waitFor(() => expect(createWorkspaceMock).toHaveBeenCalled());
    const payload = createWorkspaceMock.mock.calls[0][0];
    expect(payload.organization_slug).toBe("acme-coffee-co");
    expect(payload.brand_slug).toBe("acme-espresso");
  });
});

// ---------------------------------------------------------------------
//  Error handling
// ---------------------------------------------------------------------

describe("OnboardingWizard error handling", () => {
  it("shows 409 duplicate-slug error inline without navigating", async () => {
    createWorkspaceMock.mockRejectedValue(
      new ApiError("Organization slug 'acme' is already taken.", 409, null),
    );

    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await fillFullForm(user);

    await act(async () => {
      await user.click(screen.getByTestId("wizard-submit"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("wizard-error")).toHaveTextContent(
        /already taken/,
      );
    });
    expect(routerPush).not.toHaveBeenCalled();
    // Draft survives so user can edit + retry.
    expect(window.localStorage.getItem(WIZARD_STORAGE_KEY)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------
//  Persona step (P-series)
// ---------------------------------------------------------------------

describe("OnboardingWizard persona step", () => {
  it("renders persona pickers on step 4 with Next enabled (optional)", async () => {
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await advanceTo(user, 4);

    expect(screen.getByTestId("wizard-persona")).toBeInTheDocument();
    // All 6 persona options present.
    for (const v of [
      "solo_founder",
      "in_house_marketer",
      "agency",
      "freelancer",
      "consultant",
      "other",
    ]) {
      expect(screen.getByTestId(`persona-${v}`)).toBeInTheDocument();
    }
    // Next is enabled even with no selection (optional step).
    expect(
      (screen.getByTestId("wizard-next") as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("selecting and re-clicking a persona toggles it off", async () => {
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await advanceTo(user, 4);

    const agency = screen.getByTestId("persona-agency");
    await user.click(agency);
    expect(agency.getAttribute("aria-pressed")).toBe("true");
    await user.click(agency);
    expect(agency.getAttribute("aria-pressed")).toBe("false");
  });

  it("submit payload includes the chosen persona", async () => {
    createWorkspaceMock.mockResolvedValue({
      organization_id: "o",
      organization_slug: "acme",
      organization_name: "Acme",
      brand_id: "b",
      brand_slug: "main",
      brand_name: "Main",
      member_id: "m",
      role_slugs: ["owner"],
    });

    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await startWizard(user);
    // Fill steps 1-3.
    await waitFor(() =>
      expect(screen.getByTestId("field-business-name")).toBeInTheDocument(),
    );
    await user.type(screen.getByTestId("field-business-name"), "Acme");
    await user.click(screen.getByTestId("wizard-next")); // → 2
    await user.type(screen.getByTestId("field-brand-name"), "Espresso");
    await user.click(screen.getByTestId("wizard-next")); // → 3
    await user.click(screen.getByTestId("goal-leads"));
    await user.click(screen.getByTestId("wizard-next")); // → 4 (Persona)
    // Pick agency.
    await user.click(screen.getByTestId("persona-agency"));
    await user.click(screen.getByTestId("wizard-next")); // → 5 (Review)

    await act(async () => {
      await user.click(screen.getByTestId("wizard-submit"));
    });

    await waitFor(() => expect(createWorkspaceMock).toHaveBeenCalled());
    expect(createWorkspaceMock.mock.calls[0][0]).toMatchObject({
      persona: "agency",
    });
  });

  it("submit payload has persona: null when user skips the step", async () => {
    createWorkspaceMock.mockResolvedValue({
      organization_id: "o",
      organization_slug: "acme",
      organization_name: "Acme",
      brand_id: "b",
      brand_slug: "main",
      brand_name: "Main",
      member_id: "m",
      role_slugs: ["owner"],
    });

    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await fillFullForm(user); // helper skips persona

    await act(async () => {
      await user.click(screen.getByTestId("wizard-submit"));
    });

    await waitFor(() => expect(createWorkspaceMock).toHaveBeenCalled());
    expect(createWorkspaceMock.mock.calls[0][0].persona).toBeNull();
  });
});

// ---------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------

// The wizard opens on a welcome gate; click "Create your workspace" to reach
// the form. No-op on resume / org-only paths where the gate is skipped.
async function startWizard(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByTestId("onboarding-wizard");
  const start = screen.queryByTestId("onboarding-start");
  if (start) await user.click(start);
}

async function fillFullForm(user: ReturnType<typeof userEvent.setup>) {
  await startWizard(user);
  await waitFor(() =>
    expect(screen.getByTestId("field-business-name")).toBeInTheDocument(),
  );

  await user.type(screen.getByTestId("field-business-name"), "Acme");
  await user.type(screen.getByTestId("field-industry"), "Cafe");
  await user.click(screen.getByTestId("wizard-next")); // → 2

  await user.type(screen.getByTestId("field-brand-name"), "Espresso");
  await user.type(
    screen.getByTestId("field-target-audience"),
    "Young professionals buying coffee on commute",
  );
  await user.click(screen.getByTestId("wizard-next")); // → 3

  await user.click(screen.getByTestId("goal-leads"));
  await user.click(screen.getByTestId("platform-instagram"));
  await user.click(screen.getByTestId("tone-friendly"));
  await user.click(screen.getByTestId("wizard-next")); // → 4 (Persona)

  // Persona step is optional — skip without picking to land on Review (5).
  await user.click(screen.getByTestId("wizard-next")); // → 5 (Review)
}

async function advanceTo(
  user: ReturnType<typeof userEvent.setup>,
  step: 2 | 3 | 4 | 5,
) {
  await startWizard(user);
  await waitFor(() =>
    expect(screen.getByTestId("field-business-name")).toBeInTheDocument(),
  );
  await user.type(screen.getByTestId("field-business-name"), "Acme");
  await user.click(screen.getByTestId("wizard-next")); // → 2
  if (step === 2) return;
  await user.type(screen.getByTestId("field-brand-name"), "Espresso");
  await user.click(screen.getByTestId("wizard-next")); // → 3
  if (step === 3) return;
  await user.click(screen.getByTestId("goal-leads"));
  await user.click(screen.getByTestId("wizard-next")); // → 4 (Persona)
  if (step === 4) return;
  // Persona is optional — skip without picking.
  await user.click(screen.getByTestId("wizard-next")); // → 5 (Review)
}

// ---------------------------------------------------------------------
//  StrictMode boot (regression — permanent "Loading…" deadlock)
// ---------------------------------------------------------------------

describe("StrictMode boot", () => {
  // React 18/19 dev StrictMode double-invokes effects. A previous version
  // gated the /me-preflight setState behind an `alive` flag whose cleanup
  // (run between the two invocations) permanently suppressed the state
  // update — leaving the wizard stuck on "Loading…" forever for any user
  // with no memberships. This pins the fix.
  it("reaches the interactive form under StrictMode (no membership)", async () => {
    meMock.mockResolvedValue(NO_MEMBERSHIPS_ME);

    render(
      <StrictMode>
        <OnboardingWizard />
      </StrictMode>,
    );

    // Boot must complete: the welcome gate appears and loading is gone.
    const start = await screen.findByTestId("onboarding-start");
    expect(
      screen.queryByTestId("onboarding-wizard-loading"),
    ).not.toBeInTheDocument();

    // Clicking through the gate reaches the interactive form.
    const user = userEvent.setup();
    await user.click(start);
    await waitFor(() =>
      expect(screen.getByTestId("field-business-name")).toBeInTheDocument(),
    );
    // Preflight runs exactly once despite the double-invoke.
    expect(meMock).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------
//  Welcome gate (explicit "Create your workspace" click before the form)
// ---------------------------------------------------------------------

describe("OnboardingWizard welcome gate", () => {
  it("shows the welcome gate, not the form, on a fresh visit", async () => {
    meMock.mockResolvedValue(NO_MEMBERSHIPS_ME);
    render(<OnboardingWizard />);
    expect(await screen.findByTestId("onboarding-start")).toBeInTheDocument();
    expect(
      screen.queryByTestId("field-business-name"),
    ).not.toBeInTheDocument();
  });

  it("reveals the form only after clicking Create your workspace", async () => {
    meMock.mockResolvedValue(NO_MEMBERSHIPS_ME);
    render(<OnboardingWizard />);
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("onboarding-start"));
    await waitFor(() =>
      expect(screen.getByTestId("field-business-name")).toBeInTheDocument(),
    );
  });

  it("skips the gate when resuming an in-progress draft", async () => {
    window.localStorage.setItem(
      WIZARD_STORAGE_KEY,
      JSON.stringify({
        step: 2,
        business_name: "Persisted Acme",
        industry: "",
        website: "",
        brand_name: "Persisted Brand",
        brand_description: "",
        target_audience: "",
        primary_goal: "",
        preferred_platforms: [],
        brand_tone: "",
      }),
    );
    render(<OnboardingWizard />);
    await waitFor(() =>
      expect(screen.getByTestId("field-brand-name")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("onboarding-start")).not.toBeInTheDocument();
  });
});
