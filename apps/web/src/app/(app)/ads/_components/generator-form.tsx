"use client";

import {
  Facebook,
  Instagram,
  Linkedin,
  Loader2,
  Search,
  Sparkles,
} from "lucide-react";

import { LandingPagePicker } from "@/components/landing-page-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { AdObjective, AdType } from "@/lib/api";
import { cn } from "@/lib/utils";

export type FormState = {
  ad_type: AdType;
  objective: AdObjective;
  goal: string;
  tone: string;
  audience_override: string;
  landing_page_id: string | null;
};

const TYPE_OPTIONS: {
  value: AdType;
  label: string;
  platform: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  {
    value: "meta",
    label: "Meta Ads",
    platform: "Facebook / Instagram feed",
    icon: Facebook,
  },
  {
    value: "google_search",
    label: "Google Search Ads",
    platform: "Responsive search ads (RSA)",
    icon: Search,
  },
  {
    value: "instagram_promo",
    label: "Instagram Promo",
    platform: "Stories & Reels ads",
    icon: Instagram,
  },
  {
    value: "linkedin",
    label: "LinkedIn Ads",
    platform: "Sponsored content",
    icon: Linkedin,
  },
];

const OBJECTIVE_OPTIONS: { value: AdObjective; label: string; hint: string }[] = [
  { value: "awareness", label: "Awareness", hint: "Reach, recall" },
  { value: "traffic", label: "Traffic", hint: "Clicks to a destination" },
  { value: "engagement", label: "Engagement", hint: "Comments, saves, shares" },
  { value: "leads", label: "Leads", hint: "Email / phone capture" },
  { value: "app_installs", label: "App installs", hint: "Store installs" },
  { value: "conversions", label: "Conversions", hint: "Signups, demos, trials" },
  { value: "sales", label: "Sales", hint: "Direct revenue" },
];

const GOAL_PRESETS = [
  "Drive sales",
  "Generate qualified leads",
  "Launch a new product",
  "Build brand awareness",
  "Drive app installs",
  "Re-engage past customers",
  "Promote a limited-time offer",
];

export function GeneratorForm({
  value,
  onChange,
  generating,
  onGenerate,
}: {
  value: FormState;
  onChange: (next: FormState) => void;
  generating: boolean;
  onGenerate: () => void;
}) {
  const set = <K extends keyof FormState>(key: K, v: FormState[K]) =>
    onChange({ ...value, [key]: v });

  const canSubmit = !generating && value.goal.trim().length >= 2;

  return (
    <Card>
      <CardContent className="space-y-6 pt-6">
        <section className="space-y-2">
          <Label>Ad type</Label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {TYPE_OPTIONS.map((opt) => {
              const Icon = opt.icon;
              const active = value.ad_type === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => set("ad_type", opt.value)}
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
                    {opt.platform}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="space-y-2">
          <Label>Funnel objective</Label>
          <p className="text-xs text-muted-foreground">
            The funnel stage. Drives copy strategy more than the goal does.
          </p>
          <div className="flex flex-wrap gap-2">
            {OBJECTIVE_OPTIONS.map((opt) => {
              const active = value.objective === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => set("objective", opt.value)}
                  className={cn(
                    "rounded-md border px-3 py-1.5 text-left transition-colors",
                    active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input hover:bg-accent",
                  )}
                  title={opt.hint}
                >
                  <div className="text-sm font-medium">{opt.label}</div>
                  <div
                    className={cn(
                      "text-[10px]",
                      active
                        ? "text-primary-foreground/80"
                        : "text-muted-foreground",
                    )}
                  >
                    {opt.hint}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="space-y-2">
          <Label>Campaign goal</Label>
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
            placeholder="Or type a custom goal…"
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
            Narrow the targeting for this specific ad. Leave blank to use the
            audience from onboarding.
          </p>
          <Textarea
            id="audience-override"
            rows={3}
            value={value.audience_override}
            onChange={(e) => set("audience_override", e.target.value)}
            placeholder="e.g. Existing customers who bought a subscription in the last 60 days"
          />
        </section>

        <LandingPagePicker
          value={value.landing_page_id}
          onChange={(id) => set("landing_page_id", id)}
          helperText="Every click on this ad will land here — and show up as a tracked customer when they sign up."
        />

        <div className="flex justify-end">
          <Button
            onClick={onGenerate}
            disabled={!canSubmit}
            className="min-w-[140px]"
          >
            {generating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating image…
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Generate ad
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
