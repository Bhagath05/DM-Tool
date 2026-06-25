"use client";

import {
  ArrowLeft,
  ArrowRight,
  Loader2,
  Sparkles,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useReducer, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, type BusinessProfileSubmitPayload } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  validateAudience,
  validateBusinessName,
  validateIndustry,
  validatePlatformRelevance,
  validateTractionVsGoal,
} from "@/lib/validation/profile";

/**
 * Phase 2.0 — Conversational onboarding.
 *
 * Replaces the form-heavy wizard with a calm, one-question-per-screen
 * stepper. The state shape is deliberately separate from the legacy
 * `OnboardingFormValues` so changes here don't ripple into the classic
 * wizard (which is preserved at /onboarding/profile/classic for fallback).
 *
 * What we collect (vs. what the API still requires):
 *   COLLECTED        →  PAYLOAD MAPPING
 *   business_name    →  business_name
 *   industry         →  industry
 *   what_you_sell    →  target_audience  (re-purposed: audience-of-buyers narrative)
 *   business_location→  business_location
 *   leads_band       →  current_monthly_leads_band
 *   budget_band      →  monthly_budget_band
 *   primary_goal     →  primary_goal_text + synthesised into goals[]
 *   platforms        →  preferred_platforms
 *
 * The legacy required fields `brand_tone` and `competitors` are seeded
 * with safe defaults — the Phase 2.1 Intelligence Engine refines them.
 */

const STORAGE_KEY = "aicmo:onboarding-conversational:v1";
const STEP_COUNT = 6;

// ---------------- chips & presets ----------------

const INDUSTRY_HINTS = [
  "Cafe / Restaurant",
  "Online store",
  "SaaS / Software",
  "Coaching",
  "Agency",
  "Local services",
  "Creator / Studio",
];

const LEADS_BANDS = [
  { value: "starting", label: "Just starting", hint: "0 customers yet" },
  { value: "1-50", label: "1 – 50", hint: "Early traction" },
  { value: "50-500", label: "50 – 500", hint: "Growing" },
  { value: "500-5000", label: "500 – 5,000", hint: "Scaling" },
  { value: "5000+", label: "5,000+", hint: "Established" },
] as const;

const BUDGET_BANDS = [
  { value: "0", label: "Nothing yet", hint: "Organic only" },
  { value: "under-200", label: "Under $200", hint: "Testing the waters" },
  { value: "200-1000", label: "$200 – $1,000", hint: "Steady spend" },
  { value: "1000-5000", label: "$1k – $5k", hint: "Serious growth" },
  { value: "5000+", label: "$5k+", hint: "Full-funnel" },
] as const;

const GOAL_PRESETS = [
  "Get my first 10 customers",
  "Generate qualified leads",
  "Drive sales",
  "Build brand awareness",
  "Launch a new product",
  "Grow my email list",
  "Re-engage past customers",
];

const PLATFORM_OPTIONS = [
  "Instagram",
  "TikTok",
  "LinkedIn",
  "YouTube",
  "Facebook",
  "X (Twitter)",
  "Pinterest",
  "Email",
];

// ---------------- state ----------------

type FlowState = {
  step: number;
  business_name: string;
  industry: string;
  what_you_sell: string;
  business_location: string;
  leads_band: string;
  budget_band: string;
  primary_goal: string;
  platforms: string[];
};

const INITIAL_STATE: FlowState = {
  step: 0,
  business_name: "",
  industry: "",
  what_you_sell: "",
  business_location: "",
  leads_band: "",
  budget_band: "",
  primary_goal: "",
  platforms: [],
};

type Action =
  | { type: "set"; key: keyof FlowState; value: string | string[] }
  | { type: "next" }
  | { type: "back" }
  | { type: "hydrate"; payload: Partial<FlowState> };

function reducer(state: FlowState, action: Action): FlowState {
  switch (action.type) {
    case "set":
      return { ...state, [action.key]: action.value };
    case "next":
      return { ...state, step: Math.min(STEP_COUNT - 1, state.step + 1) };
    case "back":
      return { ...state, step: Math.max(0, state.step - 1) };
    case "hydrate":
      return { ...state, ...action.payload };
    default:
      return state;
  }
}

// ---------------- validation ----------------

function canAdvance(state: FlowState): boolean {
  switch (state.step) {
    case 0:
      // Required: business_name (2+) + industry (2+)
      return (
        state.business_name.trim().length >= 2 &&
        state.industry.trim().length >= 2
      );
    case 1:
      // Required: at least 10 chars (matches backend min_length on target_audience)
      return state.what_you_sell.trim().length >= 10;
    case 2:
    case 3:
    case 4:
      // Location / leads / budget are skippable.
      return true;
    case 5:
      // Need at least one goal source + one platform.
      return (
        state.primary_goal.trim().length >= 2 && state.platforms.length >= 1
      );
    default:
      return true;
  }
}

function isSkippable(step: number): boolean {
  return step >= 2 && step <= 4;
}

// ---------------- payload mapping ----------------

function toPayload(state: FlowState): BusinessProfileSubmitPayload {
  const goal = state.primary_goal.trim();
  return {
    business_name: state.business_name.trim(),
    industry: state.industry.trim(),
    target_audience: state.what_you_sell.trim(),
    // Legacy required fields — seeded with safe defaults; Intelligence
    // Engine v2 (Phase 2.1) will refine brand_tone + competitors.
    brand_tone: "Professional",
    competitors: [],
    goals: goal ? [goal] : [],
    preferred_platforms: state.platforms,
    business_location: state.business_location.trim() || undefined,
    current_monthly_leads_band: state.leads_band || undefined,
    monthly_budget_band: state.budget_band || undefined,
    primary_goal_text: goal || undefined,
  };
}

// ---------------- component ----------------

export function ConversationalFlow() {
  const router = useRouter();
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Hydrate draft on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as Partial<FlowState>;
      // Don't restore step — always restart at 0 so the user re-confirms.
      const { step: _ignored, ...rest } = parsed;
      void _ignored;
      dispatch({ type: "hydrate", payload: rest });
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  // Persist on change.
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* quota — ignore */
    }
  }, [state]);

  const onSubmit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await api.business.submit(toPayload(state));
      window.localStorage.removeItem(STORAGE_KEY);
      router.replace("/dashboard");
      router.refresh();
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Couldn't save your profile");
      setSubmitting(false);
    }
  };

  const onNext = () => {
    if (!canAdvance(state) && !isSkippable(state.step)) return;
    if (state.step === STEP_COUNT - 1) {
      void onSubmit();
      return;
    }
    dispatch({ type: "next" });
  };

  const onSkip = () => {
    if (!isSkippable(state.step)) return;
    if (state.step === 2) dispatch({ type: "set", key: "business_location", value: "" });
    if (state.step === 3) dispatch({ type: "set", key: "leads_band", value: "" });
    if (state.step === 4) dispatch({ type: "set", key: "budget_band", value: "" });
    dispatch({ type: "next" });
  };

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-2xl flex-col">
      <ProgressBar current={state.step} total={STEP_COUNT} />

      <div className="flex flex-1 flex-col justify-center py-8">
        <StepContent state={state} dispatch={dispatch} />
      </div>

      {submitError && (
        <p className="mb-3 text-sm text-destructive" role="alert">
          {submitError}
        </p>
      )}

      <FooterNav
        step={state.step}
        canAdvance={canAdvance(state)}
        submitting={submitting}
        onBack={() => dispatch({ type: "back" })}
        onSkip={onSkip}
        onNext={onNext}
        isLast={state.step === STEP_COUNT - 1}
        skippable={isSkippable(state.step)}
      />
    </div>
  );
}

// ---------------- subcomponents ----------------

function ProgressBar({ current, total }: { current: number; total: number }) {
  const pct = Math.round(((current + 1) / total) * 100);
  return (
    <div className="space-y-1.5 pt-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          Step {current + 1} of {total}
        </span>
        <span>{pct}%</span>
      </div>
      <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function StepShell({
  eyebrow,
  question,
  helper,
  children,
}: {
  eyebrow: string;
  question: string;
  helper: string;
  children: React.ReactNode;
}) {
  return (
    <div className="animate-in fade-in slide-in-from-bottom-2 duration-500 space-y-6">
      <div className="space-y-2">
        <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {eyebrow}
        </div>
        <h1 className="text-3xl font-semibold tracking-tight leading-tight sm:text-4xl">
          {question}
        </h1>
        <p className="text-base text-muted-foreground">{helper}</p>
      </div>
      <div>{children}</div>
    </div>
  );
}

function StepContent({
  state,
  dispatch,
}: {
  state: FlowState;
  dispatch: React.Dispatch<Action>;
}) {
  const set = (key: keyof FlowState, value: string | string[]) =>
    dispatch({ type: "set", key, value });

  switch (state.step) {
    case 0: {
      const nameHint = validateBusinessName(state.business_name);
      const industryHint = validateIndustry(state.industry);
      return (
        <StepShell
          eyebrow="Tell us about your business"
          question="What do you call it, and what kind of business is it?"
          helper="Don't overthink it — a few words is fine."
        >
          <div className="space-y-4">
            <div className="space-y-1">
              <Input
                autoFocus
                value={state.business_name}
                onChange={(e) => set("business_name", e.target.value)}
                placeholder="Business name — e.g. Brookie Bar"
                className="h-12 text-base"
                maxLength={255}
              />
              {!nameHint.ok && (
                <p className="px-1 text-xs text-muted-foreground">
                  {nameHint.hint}
                </p>
              )}
            </div>
            <div className="space-y-1">
              <Input
                value={state.industry}
                onChange={(e) => set("industry", e.target.value)}
                placeholder="What kind of business — e.g. Cafe"
                className="h-12 text-base"
                maxLength={128}
              />
              {!industryHint.ok && (
                <p className="px-1 text-xs text-muted-foreground">
                  {industryHint.hint}
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2 pt-1">
              {INDUSTRY_HINTS.map((h) => (
                <ChipButton
                  key={h}
                  active={state.industry === h}
                  onClick={() => set("industry", h)}
                  label={h}
                />
              ))}
            </div>
          </div>
        </StepShell>
      );
    }

    case 1: {
      const audienceHint = validateAudience(state.what_you_sell);
      return (
        <StepShell
          eyebrow="Your customers"
          question="Who is it for?"
          helper="A sentence or two. The AI uses this to ground every piece of content."
        >
          <Textarea
            autoFocus
            value={state.what_you_sell}
            onChange={(e) => set("what_you_sell", e.target.value)}
            placeholder="e.g. Coffee-loving professionals in Hyderabad aged 25-40 who care about quality and don't mind paying a small premium for it"
            className="min-h-[140px] text-base"
            maxLength={2000}
          />
          <p className="mt-2 px-1 text-xs text-muted-foreground">
            {audienceHint.ok
              ? state.what_you_sell.trim().length >= 10
                ? "Looks good — specific enough for the AI to ground on."
                : ""
              : audienceHint.hint}
          </p>
        </StepShell>
      );
    }

    case 2:
      return (
        <StepShell
          eyebrow="Location"
          question="Where are you based?"
          helper="Helps the AI think about regional trends and audiences. Skip if it doesn't matter."
        >
          <Input
            autoFocus
            value={state.business_location}
            onChange={(e) => set("business_location", e.target.value)}
            placeholder="e.g. Hyderabad, India  ·  Remote / Global"
            className="h-12 text-base"
            maxLength={255}
          />
        </StepShell>
      );

    case 3:
      return (
        <StepShell
          eyebrow="Current traction"
          question="How many leads or customers do you get a month right now?"
          helper="Honest answer — there's no wrong number. We use this to set realistic growth targets."
        >
          <div className="grid gap-2 sm:grid-cols-2">
            {LEADS_BANDS.map((b) => (
              <CardChoice
                key={b.value}
                active={state.leads_band === b.value}
                onClick={() => set("leads_band", b.value)}
                label={b.label}
                hint={b.hint}
              />
            ))}
          </div>
        </StepShell>
      );

    case 4:
      return (
        <StepShell
          eyebrow="Budget"
          question="What's your monthly marketing budget?"
          helper="We'll plan recommendations against what you can actually spend."
        >
          <div className="grid gap-2 sm:grid-cols-2">
            {BUDGET_BANDS.map((b) => (
              <CardChoice
                key={b.value}
                active={state.budget_band === b.value}
                onClick={() => set("budget_band", b.value)}
                label={b.label}
                hint={b.hint}
              />
            ))}
          </div>
        </StepShell>
      );

    case 5: {
      const tractionHint = validateTractionVsGoal(
        state.leads_band || null,
        state.primary_goal,
      );
      const platformHint = validatePlatformRelevance(
        state.industry,
        state.platforms,
      );
      return (
        <StepShell
          eyebrow="Where you want to go"
          question="What's the one thing you want from us right now?"
          helper="Plus the platforms you actually use. Last step — the AI takes it from here."
        >
          <div className="space-y-6">
            <div className="space-y-3">
              <Input
                autoFocus
                value={state.primary_goal}
                onChange={(e) => set("primary_goal", e.target.value)}
                placeholder="e.g. Get 50 customers in the next 3 months"
                className="h-12 text-base"
                maxLength={500}
              />
              <div className="flex flex-wrap gap-2">
                {GOAL_PRESETS.map((g) => (
                  <ChipButton
                    key={g}
                    active={state.primary_goal === g}
                    onClick={() => set("primary_goal", g)}
                    label={g}
                  />
                ))}
              </div>
              {!tractionHint.ok && (
                <p className="px-1 text-xs text-muted-foreground">
                  {tractionHint.hint}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <div className="text-sm font-medium">
                Which platforms do you (or plan to) use?
              </div>
              <div className="flex flex-wrap gap-2">
                {PLATFORM_OPTIONS.map((p) => {
                  const active = state.platforms.includes(p);
                  return (
                    <ChipButton
                      key={p}
                      active={active}
                      onClick={() => {
                        const next = active
                          ? state.platforms.filter((x) => x !== p)
                          : [...state.platforms, p];
                        set("platforms", next);
                      }}
                      label={p}
                    />
                  );
                })}
              </div>
              {!platformHint.ok && (
                <p className="px-1 text-xs text-muted-foreground">
                  {platformHint.hint}
                </p>
              )}
            </div>
          </div>
        </StepShell>
      );
    }

    default:
      return null;
  }
}

function FooterNav({
  step,
  canAdvance,
  submitting,
  isLast,
  skippable,
  onBack,
  onSkip,
  onNext,
}: {
  step: number;
  canAdvance: boolean;
  submitting: boolean;
  isLast: boolean;
  skippable: boolean;
  onBack: () => void;
  onSkip: () => void;
  onNext: () => void;
}) {
  return (
    <div className="flex items-center justify-between border-t pt-4">
      <Button
        type="button"
        variant="ghost"
        onClick={onBack}
        disabled={step === 0 || submitting}
        className="text-muted-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back
      </Button>

      <div className="flex items-center gap-2">
        {skippable && (
          <button
            type="button"
            onClick={onSkip}
            disabled={submitting}
            className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline disabled:opacity-50"
          >
            Skip — AI will figure this out
          </button>
        )}
        <Button
          type="button"
          onClick={onNext}
          disabled={(!canAdvance && !skippable) || submitting}
          className="min-w-[120px]"
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Setting up…
            </>
          ) : isLast ? (
            <>
              <Sparkles className="h-4 w-4" />
              Finish
            </>
          ) : (
            <>
              Continue
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

function ChipButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3.5 py-1.5 text-xs transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-input bg-background hover:bg-accent",
      )}
    >
      {label}
    </button>
  );
}

function CardChoice({
  active,
  onClick,
  label,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md border px-4 py-3 text-left transition-colors",
        active
          ? "border-primary bg-accent"
          : "border-input bg-background hover:bg-accent/50",
      )}
    >
      <div className="text-sm font-medium">{label}</div>
      <div className="text-xs text-muted-foreground">{hint}</div>
    </button>
  );
}
