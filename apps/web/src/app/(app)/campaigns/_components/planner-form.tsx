"use client";

import {
  CalendarDays,
  Loader2,
  Megaphone,
  Repeat,
  Rocket,
  Sparkles,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";

import { LandingPagePicker } from "@/components/landing-page-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { CampaignDuration, CampaignType } from "@/lib/api";
import { cn } from "@/lib/utils";

export type FormState = {
  campaign_type: CampaignType;
  duration_days: CampaignDuration;
  platforms: string[];
  goal: string;
  tone: string;
  audience_override: string;
  landing_page_id: string | null;
};

const TYPE_OPTIONS: {
  value: CampaignType;
  label: string;
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  {
    value: "product_launch",
    label: "Product launch",
    hint: "Pre-launch build, launch day, post-launch sustain",
    icon: Rocket,
  },
  {
    value: "brand_awareness",
    label: "Brand awareness",
    hint: "Top-of-funnel reach + recall",
    icon: Megaphone,
  },
  {
    value: "lead_generation",
    label: "Lead generation",
    hint: "Value-first, escalating CTAs to opt-in",
    icon: Target,
  },
  {
    value: "seasonal",
    label: "Seasonal",
    hint: "Time-bound moment — build, peak, extend",
    icon: CalendarDays,
  },
  {
    value: "engagement_growth",
    label: "Engagement growth",
    hint: "Conversation, saves, shares",
    icon: TrendingUp,
  },
  {
    value: "retargeting",
    label: "Retargeting",
    hint: "Re-warm existing audience, address objections",
    icon: Repeat,
  },
];

const DURATION_OPTIONS: { value: CampaignDuration; label: string }[] = [
  { value: 7, label: "7 days" },
  { value: 14, label: "14 days" },
  { value: 30, label: "30 days" },
];

const GOAL_PRESETS = [
  "Drive launch-day revenue",
  "Generate qualified leads",
  "Hit 25k followers",
  "Win 1000 newsletter subscribers",
  "Recover dormant customers",
  "Build brand recall",
  "Launch waitlist",
];

export function PlannerForm({
  value,
  onChange,
  availablePlatforms,
  generating,
  onGenerate,
}: {
  value: FormState;
  onChange: (next: FormState) => void;
  availablePlatforms: string[];
  generating: boolean;
  onGenerate: () => void;
}) {
  const set = <K extends keyof FormState>(key: K, v: FormState[K]) =>
    onChange({ ...value, [key]: v });

  const togglePlatform = (p: string, on: boolean) => {
    const next = on
      ? Array.from(new Set([...value.platforms, p]))
      : value.platforms.filter((x) => x !== p);
    set("platforms", next);
  };

  const canSubmit =
    !generating &&
    value.platforms.length > 0 &&
    value.goal.trim().length >= 2;

  return (
    <Card>
      <CardContent className="space-y-6 pt-6">
        <section className="space-y-2">
          <Label>Campaign type</Label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {TYPE_OPTIONS.map((opt) => {
              const Icon = opt.icon;
              const active = value.campaign_type === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => set("campaign_type", opt.value)}
                  className={cn(
                    "rounded-md border p-3 text-left transition-colors",
                    active
                      ? "border-primary bg-accent"
                      : "border-input hover:bg-accent",
                  )}
                >
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <div className="mt-2 text-sm font-medium">{opt.label}</div>
                  <div className="text-xs text-muted-foreground">
                    {opt.hint}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="space-y-2">
          <Label>Duration</Label>
          <div className="flex flex-wrap gap-2">
            {DURATION_OPTIONS.map((opt) => {
              const active = value.duration_days === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => set("duration_days", opt.value)}
                  className={cn(
                    "rounded-md border px-4 py-1.5 text-sm transition-colors",
                    active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input hover:bg-accent",
                  )}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </section>

        <section className="space-y-2">
          <Label className="flex items-center gap-2">
            <Users className="h-3.5 w-3.5 text-muted-foreground" />
            Platforms for this campaign
          </Label>
          <p className="text-xs text-muted-foreground">
            Subset of your preferred platforms. The planner will only schedule
            posts on what you tick here.
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {availablePlatforms.map((p) => {
              const active = value.platforms.includes(p);
              return (
                <label
                  key={p}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors",
                    active
                      ? "border-primary bg-accent"
                      : "border-input hover:bg-accent",
                  )}
                >
                  <Checkbox
                    checked={active}
                    onCheckedChange={(v) => togglePlatform(p, v === true)}
                  />
                  {p}
                </label>
              );
            })}
          </div>
        </section>

        <section className="space-y-2">
          <Label>Top-level goal</Label>
          <div className="flex flex-wrap gap-2">
            {GOAL_PRESETS.map((g) => {
              const active = value.goal === g;
              return (
                <button
                  key={g}
                  type="button"
                  onClick={() => set("goal", g)}
                  className={cn(
                    "rounded-md border px-3 py-1 text-xs transition-colors",
                    active
                      ? "border-primary bg-accent"
                      : "border-input hover:bg-accent",
                  )}
                >
                  {g}
                </button>
              );
            })}
          </div>
          <Input
            value={value.goal}
            onChange={(e) => set("goal", e.target.value)}
            placeholder="Or type a specific goal…"
          />
        </section>

        <section className="space-y-2">
          <Label htmlFor="tone-override">Tone override (optional)</Label>
          <Input
            id="tone-override"
            value={value.tone}
            onChange={(e) => set("tone", e.target.value)}
            placeholder="Leave blank to use brand tone from onboarding"
          />
        </section>

        <section className="space-y-2">
          <Label htmlFor="audience-override">
            Audience override (optional)
          </Label>
          <p className="text-xs text-muted-foreground">
            Narrow the audience for this specific campaign.
          </p>
          <Textarea
            id="audience-override"
            rows={3}
            value={value.audience_override}
            onChange={(e) => set("audience_override", e.target.value)}
            placeholder="e.g. Existing customers in EU, lapsed >90 days"
          />
        </section>

        <LandingPagePicker
          value={value.landing_page_id}
          onChange={(id) => set("landing_page_id", id)}
          helperText="Every day in your plan gets its own unique link — so you'll know exactly which day brought in which customer."
        />

        <div className="flex justify-end">
          <Button
            onClick={onGenerate}
            disabled={!canSubmit}
            className="min-w-[160px]"
          >
            {generating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Planning…
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Generate plan
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
