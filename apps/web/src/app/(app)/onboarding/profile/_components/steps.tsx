"use client";

import { useFormContext } from "react-hook-form";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  BRAND_TONES,
  PLATFORMS,
  type OnboardingFormValues,
} from "@/lib/onboarding-schema";
import { cn } from "@/lib/utils";

function FieldRow({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export function StepBusiness() {
  const {
    register,
    formState: { errors },
  } = useFormContext<OnboardingFormValues>();
  return (
    <div className="space-y-5">
      <FieldRow
        label="Business name"
        error={errors.business_name?.message}
        htmlFor="business_name"
      >
        <Input
          id="business_name"
          placeholder="Acme Coffee Co."
          {...register("business_name")}
        />
      </FieldRow>
      <FieldRow
        label="Website"
        hint="Optional. Helps AI tailor analysis."
        error={errors.website?.message}
        htmlFor="website"
      >
        <Input
          id="website"
          placeholder="https://acme.coffee"
          {...register("website")}
        />
      </FieldRow>
      <FieldRow
        label="Industry"
        error={errors.industry?.message}
        htmlFor="industry"
      >
        <Input
          id="industry"
          placeholder="Specialty coffee, e-commerce"
          {...register("industry")}
        />
      </FieldRow>
    </div>
  );
}

export function StepAudience() {
  const {
    register,
    formState: { errors },
  } = useFormContext<OnboardingFormValues>();
  return (
    <FieldRow
      label="Who is your audience?"
      hint="Describe demographics, interests, pain points, and where they spend time online."
      error={errors.target_audience?.message}
      htmlFor="target_audience"
    >
      <Textarea
        id="target_audience"
        rows={6}
        placeholder="Urban professionals aged 25-40 who care about specialty coffee and sustainable sourcing…"
        {...register("target_audience")}
      />
    </FieldRow>
  );
}

export function StepCompetitors() {
  const { register } = useFormContext<OnboardingFormValues>();
  return (
    <FieldRow
      label="Competitors"
      hint="One per line — brand name or URL. Optional but improves analysis."
      htmlFor="competitors_text"
    >
      <Textarea
        id="competitors_text"
        rows={6}
        placeholder={"blueBottle.com\nstumptown.com\nintelligentsia"}
        {...register("competitors_text")}
      />
    </FieldRow>
  );
}

export function StepGoals() {
  const {
    register,
    formState: { errors },
  } = useFormContext<OnboardingFormValues>();
  return (
    <FieldRow
      label="What are your marketing goals?"
      hint="One per line. Examples: grow Instagram, drive subscriptions, build email list."
      error={errors.goals_text?.message}
      htmlFor="goals_text"
    >
      <Textarea
        id="goals_text"
        rows={6}
        placeholder={"Grow Instagram following to 25k\nDrive 200 paid subscribers in 90 days"}
        {...register("goals_text")}
      />
    </FieldRow>
  );
}

export function StepBrandTone() {
  const {
    register,
    watch,
    formState: { errors },
  } = useFormContext<OnboardingFormValues>();
  const current = watch("brand_tone");
  return (
    <div className="space-y-3">
      <Label>Brand tone</Label>
      <p className="text-xs text-muted-foreground">
        Pick the voice the AI should use across content.
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {BRAND_TONES.map((tone) => {
          const active = current === tone;
          return (
            <label
              key={tone}
              className={cn(
                "cursor-pointer rounded-md border px-3 py-2 text-sm transition-colors",
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-input hover:bg-accent",
              )}
            >
              <input
                type="radio"
                value={tone}
                {...register("brand_tone")}
                className="sr-only"
              />
              {tone}
            </label>
          );
        })}
      </div>
      {errors.brand_tone && (
        <p className="text-xs text-destructive">{errors.brand_tone.message}</p>
      )}
    </div>
  );
}

export function StepPlatforms() {
  const {
    watch,
    setValue,
    formState: { errors },
  } = useFormContext<OnboardingFormValues>();
  const selected = watch("preferred_platforms") ?? [];

  const toggle = (platform: string, on: boolean) => {
    const next = on
      ? Array.from(new Set([...selected, platform]))
      : selected.filter((p) => p !== platform);
    setValue("preferred_platforms", next, {
      shouldValidate: true,
      shouldDirty: true,
    });
  };

  return (
    <div className="space-y-3">
      <Label>Preferred platforms</Label>
      <p className="text-xs text-muted-foreground">
        Pick the platforms you want the AI to plan content for.
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {PLATFORMS.map((platform) => {
          const active = selected.includes(platform);
          return (
            <label
              key={platform}
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors",
                active ? "border-primary bg-accent" : "border-input hover:bg-accent",
              )}
            >
              <Checkbox
                checked={active}
                onCheckedChange={(v) => toggle(platform, v === true)}
              />
              {platform}
            </label>
          );
        })}
      </div>
      {errors.preferred_platforms && (
        <p className="text-xs text-destructive">
          {errors.preferred_platforms.message as string}
        </p>
      )}
    </div>
  );
}

export function StepReview() {
  const { getValues } = useFormContext<OnboardingFormValues>();
  const v = getValues();
  const competitors = (v.competitors_text ?? "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  const goals = (v.goals_text ?? "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  return (
    <div className="space-y-4 text-sm">
      <ReviewRow label="Business" value={v.business_name} />
      {v.website && <ReviewRow label="Website" value={v.website} />}
      <ReviewRow label="Industry" value={v.industry} />
      <ReviewRow label="Audience" value={v.target_audience} />
      {competitors.length > 0 && (
        <ReviewRow label="Competitors" value={competitors.join(", ")} />
      )}
      <ReviewRow label="Goals" value={goals.join(" · ")} />
      <ReviewRow label="Brand tone" value={v.brand_tone} />
      <ReviewRow
        label="Platforms"
        value={(v.preferred_platforms ?? []).join(", ")}
      />
    </div>
  );
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-3">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="whitespace-pre-wrap text-foreground">{value}</div>
    </div>
  );
}
