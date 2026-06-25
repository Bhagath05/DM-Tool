"use client";

import {
  Image as ImageIcon,
  Loader2,
  Palette,
  Play,
  Sparkles,
  StretchHorizontal,
} from "lucide-react";

import { LandingPagePicker } from "@/components/landing-page-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { VisualType } from "@/lib/api";
import { cn } from "@/lib/utils";

export type FormState = {
  visual_type: VisualType;
  platform: string;
  goal: string;
  tone: string;
  landing_page_id: string | null;
};

const TYPE_OPTIONS: {
  value: VisualType;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  hint: string;
}[] = [
  {
    value: "ad_creative",
    label: "Poster / Ad",
    icon: Palette,
    hint: "Single PNG — product hero, composition, CTA zone",
  },
  {
    value: "carousel",
    label: "Carousel",
    icon: StretchHorizontal,
    hint: "Multiple PNG slides — cover through CTA",
  },
  {
    value: "reel",
    label: "Reel",
    icon: Play,
    hint: "9:16 video (coming in Phase 4)",
  },
  {
    value: "thumbnail",
    label: "Thumbnail",
    icon: ImageIcon,
    hint: "YouTube / podcast cover PNG",
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
          <Label>Visual type</Label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {TYPE_OPTIONS.map((opt) => {
              const Icon = opt.icon;
              const active = value.visual_type === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => set("visual_type", opt.value)}
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
            From your preferred platforms.
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
          <Input
            id="tone-override"
            value={value.tone}
            onChange={(e) => set("tone", e.target.value)}
            placeholder="Leave blank to use brand tone from onboarding"
          />
        </section>

        <LandingPagePicker
          value={value.landing_page_id}
          onChange={(id) => set("landing_page_id", id)}
          helperText="When you post this visual, use the link we generate — that's how each customer it brings in shows up here later."
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
                Generate creative
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
