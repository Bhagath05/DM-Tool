"use client";

/**
 * OnboardingWizard — A4 customer-facing wizard.
 *
 * Five steps:
 *   1. Business basics      (business name, industry, website)
 *   2. Brand setup          (brand name, brand description, target audience)
 *   3. Marketing profile    (primary goal, platforms, tone)
 *   4. Review               (all fields displayed)
 *   5. Submit               (single backend call, then /dashboard)
 *
 * One backend call: POST /api/v1/orgs/workspace with the merged payload.
 * Backend creates Organization, Brand, OrganizationMember, owner role,
 * AND (when enough business-profile fields are present) BusinessProfile —
 * all in one PG transaction. See A4 backend extension.
 *
 * Strict validation per spec:
 *   - Business Name, Brand Name, Primary Goal — block Next when blank
 *   - Other fields — show but don't block
 *
 * Mount-time routing (resume / skip):
 *   - has org + brand           → router.replace("/dashboard")
 *   - has org, no brand         → start wizard at step 2 with org name
 *                                 pre-filled and step 1 marked complete
 *   - nothing                   → start at step 1
 *
 * Slugs are auto-derived from names with `slugify()` and submitted
 * silently. No slug fields visible (A4 spec).
 */

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  api,
  type OnboardingPersona,
  type OnboardingWorkspacePayload,
} from "@/lib/api";
import { slugify } from "@/lib/slugify";
import {
  writePersistedSelection,
} from "@/lib/tenant";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------
//  Constants — option lists per spec
// ---------------------------------------------------------------------

const PRIMARY_GOALS = [
  { value: "leads", label: "Leads", hint: "Capture sign-ups + inquiries" },
  { value: "sales", label: "Sales", hint: "Drive direct purchases" },
  { value: "awareness", label: "Awareness", hint: "Reach new audiences" },
  { value: "engagement", label: "Engagement", hint: "Build community + repeat traffic" },
] as const;

const PLATFORMS = [
  { value: "instagram", label: "Instagram" },
  { value: "facebook", label: "Facebook" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "google", label: "Google" },
] as const;

const BRAND_TONES = [
  { value: "professional", label: "Professional" },
  { value: "friendly", label: "Friendly" },
  { value: "luxury", label: "Luxury" },
  { value: "modern", label: "Modern" },
] as const;

// Persona — segmentation, NOT an authorization role. Keep values in
// sync with: apps/api/aicmo/modules/orgs/schemas.py (Persona Literal)
// and alembic 0019 (CHECK constraint).
const PERSONAS = [
  { value: "solo_founder", label: "Solo founder", hint: "Building it yourself" },
  { value: "in_house_marketer", label: "In-house marketer", hint: "Running marketing for one brand" },
  { value: "agency", label: "Agency", hint: "Managing multiple client brands" },
  { value: "freelancer", label: "Freelancer", hint: "Contracting for a few clients" },
  { value: "consultant", label: "Consultant", hint: "Advisory work" },
  { value: "other", label: "Other", hint: "Tell us later" },
] as const;

// ---------------------------------------------------------------------
//  State + persistence
// ---------------------------------------------------------------------

// Bumped storage key so old v2 drafts (no persona field) don't restore
// with a stale shape that misses the new step. Old drafts are dropped.
export const WIZARD_STORAGE_KEY = "aicmo.onboarding.wizard.v3";

type Step = 1 | 2 | 3 | 4 | 5;

interface WizardState {
  step: Step;

  // Step 1 — Business basics
  business_name: string;
  industry: string;
  website: string;

  // Step 2 — Brand setup
  brand_name: string;
  brand_description: string;
  target_audience: string;

  // Step 3 — Marketing profile
  primary_goal: string;
  preferred_platforms: string[];
  brand_tone: string;

  // Step 4 — Persona (segmentation, optional)
  persona: string;

  // Routing-only: set on mount when we detect an existing org-only state
  resume_with_org_id?: string | null;
}

const EMPTY: WizardState = {
  step: 1,
  business_name: "",
  industry: "",
  website: "",
  brand_name: "",
  brand_description: "",
  target_audience: "",
  primary_goal: "",
  preferred_platforms: [],
  brand_tone: "",
  persona: "",
};

function readPersistedWizard(): WizardState {
  if (typeof window === "undefined") return { ...EMPTY };
  try {
    const raw = window.localStorage.getItem(WIZARD_STORAGE_KEY);
    if (!raw) return { ...EMPTY };
    const parsed = JSON.parse(raw) as Partial<WizardState>;
    return {
      ...EMPTY,
      ...parsed,
      step: clampStep(parsed.step),
      preferred_platforms: Array.isArray(parsed.preferred_platforms)
        ? parsed.preferred_platforms.filter((p): p is string => typeof p === "string")
        : [],
    };
  } catch {
    return { ...EMPTY };
  }
}

function writePersistedWizard(s: WizardState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(WIZARD_STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* persistence is best-effort */
  }
}

function clearPersistedWizard(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(WIZARD_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

function clampStep(n: unknown): Step {
  if (n === 2 || n === 3 || n === 4 || n === 5) return n;
  return 1;
}

// ---------------------------------------------------------------------
//  Per-step validation — pure function. Strict per spec on Business
//  Name, Brand Name, Primary Goal; soft on the rest.
// ---------------------------------------------------------------------

interface StepErrors {
  business_name?: string;
  brand_name?: string;
  primary_goal?: string;
}

function validateStep(state: WizardState): StepErrors {
  const e: StepErrors = {};
  switch (state.step) {
    case 1:
      if (state.business_name.trim().length === 0) e.business_name = "Required";
      else if (state.business_name.trim().length > 120)
        e.business_name = "Max 120 characters";
      break;
    case 2:
      if (state.brand_name.trim().length === 0) e.brand_name = "Required";
      else if (state.brand_name.trim().length > 120)
        e.brand_name = "Max 120 characters";
      break;
    case 3:
      if (state.primary_goal.trim().length === 0) e.primary_goal = "Pick one";
      break;
    case 4:
      // Persona is OPTIONAL — no validation. Next is always enabled.
      break;
    case 5:
      // Review — replay every prior step's validation so we can't submit
      // a payload missing a required field. Step 4 (persona) has no
      // required fields so we skip its replay.
      return {
        ...validateStep({ ...state, step: 1 }),
        ...validateStep({ ...state, step: 2 }),
        ...validateStep({ ...state, step: 3 }),
      };
  }
  return e;
}

// ---------------------------------------------------------------------
//  Component
// ---------------------------------------------------------------------

const STEP_TITLES = [
  "About your business",
  "Set up your brand",
  "Marketing profile",
  "Who are you?",
  "Review & create",
];

type BootStatus = "loading" | "ready" | "redirecting";

export function OnboardingWizard() {
  const router = useRouter();
  const [bootStatus, setBootStatus] = useState<BootStatus>("loading");
  const [state, setState] = useState<WizardState>(EMPTY);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // `started` gates the form behind an explicit "Create your workspace" click.
  // Brand-new users see a welcome screen first; users resuming an in-progress
  // draft or an org-only setup skip straight to the form.
  const [started, setStarted] = useState(false);
  const hydrated = useRef(false);

  // Mount: check /me → skip wizard, resume at step 2, or start fresh.
  //
  // The `hydrated` ref guarantees this preflight runs exactly once, which is
  // also what makes it React-Strict-Mode-safe: under dev double-invoke, the
  // second effect bails on the ref guard. We deliberately do NOT gate the
  // resulting setState behind an `alive`/cleanup flag — doing so deadlocks the
  // boot under Strict Mode (mount #1's cleanup invalidates its own pending
  // fetch, mount #2 never re-fetches, and `bootStatus` is stuck on "loading"
  // forever → permanent "Loading…"). A late setState after a real unmount is a
  // harmless no-op in React 18/19.
  useEffect(() => {
    if (hydrated.current) return;
    hydrated.current = true;

    (async () => {
      try {
        const me = await api.me({ organizationId: null, brandId: null });

        const firstMembership = me.memberships[0] ?? null;
        const hasOrg = firstMembership !== null;
        const hasBrand = (firstMembership?.brands.length ?? 0) > 0;

        if (hasOrg && hasBrand) {
          // Spec: skip wizard entirely.
          setBootStatus("redirecting");
          router.replace("/dashboard");
          return;
        }

        // Either nothing exists, OR org-only. Start fresh from persisted
        // draft (if any), then if we detected an org-only state, jump
        // user to step 2 with the org name pre-filled.
        const persisted = readPersistedWizard();
        const resumingOrgOnly = hasOrg && !hasBrand && Boolean(firstMembership);
        const hasProgress =
          persisted.step > 1 || persisted.business_name.trim().length > 0;

        if (resumingOrgOnly && firstMembership) {
          setState({
            ...persisted,
            business_name:
              persisted.business_name || firstMembership.organization.name,
            step: persisted.step >= 2 ? persisted.step : 2,
            resume_with_org_id: firstMembership.organization.id,
          });
        } else {
          setState(persisted);
        }
        // Only brand-new users (nothing exists, no saved progress) see the
        // welcome gate. Resuming a draft or an org-only setup goes straight in.
        if (resumingOrgOnly || hasProgress) {
          setStarted(true);
        }
        setBootStatus("ready");
      } catch (err) {
        // /me failed (e.g. backend down). Fall back to a fresh wizard —
        // user can still try to submit; if backend rejects, the submit
        // error surfaces inline.
        setState(readPersistedWizard());
        setBootStatus("ready");
        if (err instanceof Error) {
          // eslint-disable-next-line no-console
          console.warn("Onboarding /me preflight failed:", err.message);
        }
      }
    })();
  }, [router]);

  // Persist on every state change after the first hydration.
  useEffect(() => {
    if (bootStatus !== "ready") return;
    writePersistedWizard(state);
  }, [state, bootStatus]);

  const errors = useMemo(() => validateStep(state), [state]);
  const stepValid = Object.keys(errors).length === 0;

  function update<K extends keyof WizardState>(key: K, value: WizardState[K]) {
    setState((s) => ({ ...s, [key]: value }));
  }

  function togglePlatform(p: string) {
    setState((s) => {
      const has = s.preferred_platforms.includes(p);
      return {
        ...s,
        preferred_platforms: has
          ? s.preferred_platforms.filter((x) => x !== p)
          : [...s.preferred_platforms, p],
      };
    });
  }

  function goBack() {
    setSubmitError(null);
    setState((s) => ({ ...s, step: clampStep((s.step - 1) as Step) }));
  }

  function goNext() {
    setSubmitError(null);
    if (!stepValid) return;
    setState((s) => ({ ...s, step: clampStep((s.step + 1) as Step) }));
  }

  async function submit() {
    setSubmitError(null);
    if (!stepValid) return;
    setSubmitting(true);
    try {
      // Auto-derive slugs silently. Backend enforces uniqueness; if
      // collision, the 409 message surfaces inline below.
      const orgSlug =
        slugify(state.business_name) || `org-${Date.now().toString(36)}`;
      const brandSlug =
        slugify(state.brand_name) || `brand-${Date.now().toString(36)}`;

      const payload: OnboardingWorkspacePayload = {
        organization_name: state.business_name.trim(),
        organization_slug: orgSlug,
        brand_name: state.brand_name.trim(),
        brand_slug: brandSlug,
        industry: state.industry.trim() || null,
        website: state.website.trim() || null,
        brand_description: state.brand_description.trim() || null,
        target_audience: state.target_audience.trim() || null,
        primary_goal: state.primary_goal || null,
        preferred_platforms: state.preferred_platforms,
        brand_tone: state.brand_tone || null,
        // Persona is optional — omitted entirely when blank so the
        // backend's Literal validator doesn't reject "" as an invalid
        // value. (It accepts null + missing; it rejects "".) The narrow
        // cast is safe because the only path that mutates state.persona
        // is the Step4Persona button list, all of whose values come
        // from PERSONAS (which mirrors OnboardingPersona exactly).
        persona: state.persona
          ? (state.persona as OnboardingPersona)
          : null,
      };
      const result = await api.onboarding.createWorkspace(payload);

      // Seed tenant cache so /dashboard's cold-boot /me carries the new
      // org/brand headers immediately. Matches W1-15 behavior.
      writePersistedSelection({
        organization_id: result.organization_id,
        brand_id: result.brand_id,
      });
      clearPersistedWizard();
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(err.message);
      } else {
        setSubmitError(err instanceof Error ? err.message : "Unknown error");
      }
      setSubmitting(false);
    }
  }

  // -------------------------------------------------------------------
  //  Render
  // -------------------------------------------------------------------

  if (bootStatus !== "ready") {
    return (
      <div
        data-testid="onboarding-wizard-loading"
        className="mx-auto flex min-h-dvh w-full max-w-2xl items-center justify-center p-6"
      >
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  // Welcome gate — the form only starts once the user explicitly clicks
  // "Create your workspace". Brand-new users land here first.
  if (!started) {
    return (
      <div
        data-testid="onboarding-wizard"
        className="mx-auto flex min-h-dvh w-full max-w-xl flex-col items-center justify-center gap-6 p-4 sm:p-8"
      >
        <div className="flex w-full flex-col items-center gap-5 rounded-lg border border-border bg-card p-8 text-center">
          <div className="flex flex-col gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">
              Welcome to DM Tool
            </h1>
            <p className="mx-auto max-w-md text-sm text-muted-foreground">
              You don&apos;t have a workspace yet. A workspace is your home in
              DM Tool — it holds your business, your brand, and everything we
              create for you. Let&apos;s set one up. It takes about a minute,
              and you can change anything later.
            </p>
          </div>
          <Button
            type="button"
            onClick={() => setStarted(true)}
            data-testid="onboarding-start"
          >
            Create your workspace →
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="onboarding-wizard"
      className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col gap-6 p-4 sm:p-8"
    >
      {/* Constant page framing — keeps "create your workspace" visible on
          every step after the user starts. */}
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Create your workspace
        </h1>
        <p className="text-sm text-muted-foreground">
          Just a few quick questions about your business and brand. You can
          change anything later.
        </p>
      </div>

      <Header step={state.step} />

      <div className="rounded-lg border border-border bg-card p-6 sm:p-8">
        <h2 className="text-lg font-semibold tracking-tight">
          {STEP_TITLES[state.step - 1]}
        </h2>

        <div className="mt-6">
          {state.step === 1 && (
            <Step1
              state={state}
              errors={errors}
              onChange={update}
            />
          )}
          {state.step === 2 && (
            <Step2 state={state} errors={errors} onChange={update} />
          )}
          {state.step === 3 && (
            <Step3
              state={state}
              errors={errors}
              onChange={update}
              onTogglePlatform={togglePlatform}
            />
          )}
          {state.step === 4 && (
            <Step4Persona state={state} onChange={update} />
          )}
          {state.step === 5 && <Step5Review state={state} />}
        </div>

        {submitError && (
          <div
            role="alert"
            data-testid="wizard-error"
            className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
          >
            {submitError}
          </div>
        )}

        <div className="mt-8 flex items-center justify-between gap-3">
          <Button
            type="button"
            variant="ghost"
            onClick={goBack}
            disabled={state.step === 1 || submitting}
            data-testid="wizard-back"
          >
            ← Back
          </Button>
          {state.step < 5 ? (
            <Button
              type="button"
              onClick={goNext}
              disabled={!stepValid}
              data-testid="wizard-next"
            >
              Continue →
            </Button>
          ) : (
            <Button
              type="button"
              onClick={submit}
              disabled={!stepValid || submitting}
              data-testid="wizard-submit"
            >
              {submitting ? "Creating workspace…" : "Create workspace"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Sub-components
// ---------------------------------------------------------------------

function Header({ step }: { step: Step }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        Step {step} of 5
      </div>
      <ol
        aria-label="Progress"
        className="flex gap-1.5"
        data-testid="wizard-progress"
      >
        {[1, 2, 3, 4, 5].map((n) => (
          <li
            key={n}
            data-active={n === step || undefined}
            data-done={n < step || undefined}
            className={cn(
              "h-1.5 flex-1 rounded-full bg-muted",
              n === step && "bg-primary",
              n < step && "bg-primary/60",
            )}
          />
        ))}
      </ol>
    </div>
  );
}

interface StepProps {
  state: WizardState;
  errors: StepErrors;
  onChange: <K extends keyof WizardState>(k: K, v: WizardState[K]) => void;
}

function Step1({ state, errors, onChange }: StepProps) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Tell us about the business this workspace is for. You can change all
        of this later.
      </p>
      <Field
        id="business-name"
        label="Business name"
        required
        value={state.business_name}
        onChange={(v) => onChange("business_name", v)}
        error={errors.business_name}
        placeholder="Acme Coffee Co."
        autoFocus
        testid="field-business-name"
      />
      <Field
        id="industry"
        label="Industry"
        value={state.industry}
        onChange={(v) => onChange("industry", v)}
        placeholder="Cafe / Restaurant, B2B SaaS, Yoga studio…"
        testid="field-industry"
        hint="Helps us tailor strategy recommendations. Recommended."
      />
      <Field
        id="website"
        label="Website"
        value={state.website}
        onChange={(v) => onChange("website", v)}
        placeholder="https://"
        testid="field-website"
        hint="Optional"
        type="url"
      />
    </div>
  );
}

function Step2({ state, errors, onChange }: StepProps) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        A brand is the unit that owns campaigns, content, and analytics.
        Most teams start with one and add more later.
      </p>
      <Field
        id="brand-name"
        label="Brand name"
        required
        value={state.brand_name}
        onChange={(v) => onChange("brand_name", v)}
        error={errors.brand_name}
        placeholder="Acme Espresso"
        autoFocus
        testid="field-brand-name"
      />
      <TextareaField
        id="brand-description"
        label="Brand description"
        value={state.brand_description}
        onChange={(v) => onChange("brand_description", v)}
        placeholder="What's distinctive about this brand?"
        testid="field-brand-description"
        rows={3}
      />
      <TextareaField
        id="target-audience"
        label="Target audience"
        value={state.target_audience}
        onChange={(v) => onChange("target_audience", v)}
        placeholder="Who buys from you most? Age, role, what they care about."
        testid="field-target-audience"
        rows={3}
        hint="At least 10 characters lets us include this in your business profile right away."
      />
    </div>
  );
}

function Step3({
  state,
  errors,
  onChange,
  onTogglePlatform,
}: StepProps & { onTogglePlatform: (p: string) => void }) {
  return (
    <div className="flex flex-col gap-6">
      {/* Primary goal — required */}
      <div className="flex flex-col gap-2">
        <Label>
          Primary goal <span className="text-destructive">*</span>
        </Label>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {PRIMARY_GOALS.map((g) => {
            const active = state.primary_goal === g.value;
            return (
              <button
                key={g.value}
                type="button"
                onClick={() => onChange("primary_goal", g.value)}
                data-testid={`goal-${g.value}`}
                data-active={active || undefined}
                className={cn(
                  "flex flex-col items-start gap-1 rounded-md border border-border bg-background p-3 text-left transition-colors",
                  "hover:bg-accent hover:text-accent-foreground",
                  active && "border-primary bg-primary/10",
                )}
              >
                <span className="text-sm font-medium">{g.label}</span>
                <span className="text-xs text-muted-foreground">{g.hint}</span>
              </button>
            );
          })}
        </div>
        {errors.primary_goal && (
          <p
            role="alert"
            data-testid="goal-error"
            className="text-xs text-destructive"
          >
            {errors.primary_goal}
          </p>
        )}
      </div>

      {/* Platforms — multi */}
      <div className="flex flex-col gap-2">
        <Label>Preferred platforms</Label>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {PLATFORMS.map((p) => {
            const checked = state.preferred_platforms.includes(p.value);
            return (
              <label
                key={p.value}
                data-testid={`platform-${p.value}`}
                data-checked={checked || undefined}
                className={cn(
                  "flex cursor-pointer items-center gap-2 rounded-md border border-border bg-background p-2 text-sm transition-colors",
                  checked && "border-primary bg-primary/10",
                )}
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => onTogglePlatform(p.value)}
                />
                <span>{p.label}</span>
              </label>
            );
          })}
        </div>
        <p className="text-xs text-muted-foreground">
          Pick the channels you actually post on. Recommended.
        </p>
      </div>

      {/* Tone — single */}
      <div className="flex flex-col gap-2">
        <Label>Tone</Label>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {BRAND_TONES.map((t) => {
            const active = state.brand_tone === t.value;
            return (
              <button
                key={t.value}
                type="button"
                onClick={() => onChange("brand_tone", t.value)}
                data-testid={`tone-${t.value}`}
                data-active={active || undefined}
                className={cn(
                  "rounded-md border border-border bg-background p-2 text-sm transition-colors",
                  "hover:bg-accent hover:text-accent-foreground",
                  active && "border-primary bg-primary/10",
                )}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Step4Persona({
  state,
  onChange,
}: {
  state: WizardState;
  onChange: <K extends keyof WizardState>(k: K, v: WizardState[K]) => void;
}) {
  return (
    <div className="flex flex-col gap-4" data-testid="wizard-persona">
      <p className="text-sm text-muted-foreground">
        This is optional — it helps us tailor the dashboard, defaults, and
        which features we surface first. Doesn&apos;t change your permissions
        (you&apos;re always the owner of workspaces you create).
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {PERSONAS.map((p) => {
          const isActive = state.persona === p.value;
          return (
            <button
              type="button"
              key={p.value}
              data-testid={`persona-${p.value}`}
              aria-pressed={isActive}
              onClick={() =>
                onChange("persona", isActive ? "" : p.value)
              }
              className={cn(
                "flex flex-col gap-1 rounded-md border p-3 text-left transition-colors",
                isActive
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-accent",
              )}
            >
              <span className="text-sm font-medium">{p.label}</span>
              <span className="text-xs text-muted-foreground">{p.hint}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Step5Review({ state }: { state: WizardState }) {
  const platformsLabel =
    state.preferred_platforms.length === 0
      ? "(none selected)"
      : state.preferred_platforms.join(", ");
  const personaLabel =
    PERSONAS.find((p) => p.value === state.persona)?.label || "—";
  return (
    <div
      className="flex flex-col gap-3 text-sm"
      data-testid="wizard-review"
    >
      <p className="text-muted-foreground">
        Everything below is created in one transaction. If anything fails,
        nothing is saved.
      </p>
      <ReviewRow label="Business" value={state.business_name} />
      <ReviewRow label="Industry" value={state.industry || "—"} />
      <ReviewRow label="Website" value={state.website || "—"} />
      <ReviewRow label="Brand" value={state.brand_name} />
      <ReviewRow
        label="Brand description"
        value={state.brand_description || "—"}
      />
      <ReviewRow
        label="Target audience"
        value={state.target_audience || "—"}
      />
      <ReviewRow label="Primary goal" value={state.primary_goal || "—"} />
      <ReviewRow label="Platforms" value={platformsLabel} />
      <ReviewRow label="Tone" value={state.brand_tone || "—"} />
      <ReviewRow label="You are" value={personaLabel} />
      <ReviewRow label="Your role" value="Owner" />
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border/60 py-2 last:border-b-0">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="text-right capitalize">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Field primitives — kept inline because the styling is wizard-specific
// ---------------------------------------------------------------------

interface FieldBaseProps {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
  placeholder?: string;
  hint?: string;
  required?: boolean;
  autoFocus?: boolean;
  testid?: string;
}

function Field({
  type = "text",
  ...rest
}: FieldBaseProps & { type?: string }) {
  return (
    <FieldWrap {...rest}>
      <Input
        id={rest.id}
        value={rest.value}
        onChange={(e) => rest.onChange(e.target.value)}
        placeholder={rest.placeholder}
        type={type}
        // eslint-disable-next-line jsx-a11y/no-autofocus
        autoFocus={rest.autoFocus}
        data-testid={rest.testid}
        aria-invalid={rest.error ? true : undefined}
        aria-describedby={
          rest.error ? `${rest.id}-error` : rest.hint ? `${rest.id}-hint` : undefined
        }
      />
    </FieldWrap>
  );
}

function TextareaField({
  rows = 3,
  ...rest
}: FieldBaseProps & { rows?: number }) {
  return (
    <FieldWrap {...rest}>
      <Textarea
        id={rest.id}
        value={rest.value}
        onChange={(e) => rest.onChange(e.target.value)}
        placeholder={rest.placeholder}
        rows={rows}
        data-testid={rest.testid}
        aria-invalid={rest.error ? true : undefined}
        aria-describedby={
          rest.error ? `${rest.id}-error` : rest.hint ? `${rest.id}-hint` : undefined
        }
      />
    </FieldWrap>
  );
}

function FieldWrap({
  id,
  label,
  error,
  hint,
  required,
  testid,
  children,
}: FieldBaseProps & { children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>
        {label}
        {required && <span className="ml-0.5 text-destructive">*</span>}
      </Label>
      {children}
      {error ? (
        <p
          id={`${id}-error`}
          role="alert"
          data-testid={testid ? `${testid}-error` : undefined}
          className="text-xs text-destructive"
        >
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
