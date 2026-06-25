"use client";

import {
  FileText,
  Loader2,
  Megaphone,
  Sparkles,
  SquarePlay,
  StretchHorizontal,
} from "lucide-react";

import { LandingPagePicker } from "@/components/landing-page-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ContentType } from "@/lib/api";
import { cn } from "@/lib/utils";

export type FormState = {
  content_type: ContentType;
  platform: string;
  goal: string;
  tone: string;
  landing_page_id: string | null;
};

const TYPE_OPTIONS: {
  value: ContentType;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  hint: string;
}[] = [
  {
    value: "social_post",
    label: "Social post",
    icon: FileText,
    hint: "One platform-native post",
  },
  {
    value: "reel",
    label: "Reel / Short",
    icon: SquarePlay,
    hint: "Hook + beats + on-screen text",
  },
  {
    value: "carousel",
    label: "Carousel",
    icon: StretchHorizontal,
    hint: "Cover + 4-10 slides",
  },
  {
    value: "ad_copy",
    label: "Ad copy",
    icon: Megaphone,
    hint: "Headline + body + CTA + targeting",
  },
];

const GOAL_PRESETS = [
  "Drive engagement",
  "Build brand awareness",
  "Drive conversions / sales",
  "Educate the audience",
  "Promote a launch",
  "Grow email list",
  "Establish thought leadership",
];

export function GeneratorForm({
  value,
  onChange,
  platforms,
  generating,
  onGenerate,
}: {
  value: FormState;
  onChange: (next: FormState) => void;
  platforms: string[];
  generating: boolean;
  onGenerate: () => void;
}) {
  const set = <K extends keyof FormState>(key: K, v: FormState[K]) =>
    onChange({ ...value, [key]: v });

  const canSubmit =
    !generating &&
    value.platform.trim().length > 0 &&
    value.goal.trim().length >= 2;

  return (
    <Card>
      <CardContent className="space-y-6 pt-6">
        <section className="space-y-2">
          <Label>Content type</Label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {TYPE_OPTIONS.map((opt) => {
              const Icon = opt.icon;
              const active = value.content_type === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => set("content_type", opt.value)}
                  className={cn(
                    "rounded-md border p-3 text-left transition-colors",
                    active
                      ? "border-primary bg-accent"
                      : "border-input hover:bg-accent",
                  )}
                >
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <div className="mt-2 text-sm font-medium">{opt.label}</div>
                  <div className="text-xs text-muted-foreground">{opt.hint}</div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="space-y-2">
          <Label>Platform</Label>
          <p className="text-xs text-muted-foreground">
            Only your preferred platforms from onboarding are shown.
          </p>
          <div className="flex flex-wrap gap-2">
            {platforms.map((p) => {
              const active = value.platform === p;
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => set("platform", p)}
                  className={cn(
                    "rounded-md border px-3 py-1.5 text-sm transition-colors",
                    active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input hover:bg-accent",
                  )}
                >
                  {p}
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
          <p className="text-xs text-muted-foreground">
            Leave blank to use your brand tone from onboarding.
          </p>
          <Input
            id="tone-override"
            value={value.tone}
            onChange={(e) => set("tone", e.target.value)}
            placeholder="e.g. punchier than usual, more technical, drier humour"
          />
        </section>

        <LandingPagePicker
          value={value.landing_page_id}
          onChange={(id) => set("landing_page_id", id)}
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
                Generating…
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Generate
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
