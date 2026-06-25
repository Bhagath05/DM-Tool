"use client";

import {
  AlertCircle,
  ArrowRight,
  CalendarDays,
  Check,
  FileText as FileTextIcon,
  Image as ImageIcon,
  Loader2,
  Megaphone,
  Package,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { LandingPagePicker } from "@/components/landing-page-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  api,
  type AdObjective,
  type BundlePiece,
  type BundlePieceKind,
  type CampaignBundle,
  type GenerateBundlePayload,
} from "@/lib/api";
import { useGenerationContext } from "@/lib/use-generation-context";
import { cn } from "@/lib/utils";

/**
 * Phase 3.1 — the "wow" surface. One click → coordinated multi-asset
 * campaign package. Reuses every existing studio (content / ads /
 * visuals / campaigns) under the hood; here we just gather inputs +
 * render the result.
 */

type FormState = {
  theme: string;
  objective: AdObjective;
  duration_days: 7 | 14 | 30;
  landing_page_id: string | null;
};

const DEFAULTS: FormState = {
  theme: "",
  objective: "leads",
  duration_days: 14,
  landing_page_id: null,
};

const OBJECTIVES: { value: AdObjective; label: string; hint: string }[] = [
  { value: "awareness", label: "Awareness", hint: "Get on people's radar" },
  { value: "traffic", label: "Traffic", hint: "Drive clicks to a page" },
  { value: "engagement", label: "Engagement", hint: "Comments, saves, shares" },
  { value: "leads", label: "Leads", hint: "Capture emails / sign-ups" },
  {
    value: "conversions",
    label: "Conversions",
    hint: "Actual customer action",
  },
  { value: "sales", label: "Sales", hint: "Direct revenue" },
];

const DURATIONS: 7[] | 14[] | 30[] = [];
// (Just to keep TS happy with the const tuple below.)
void DURATIONS;
const DURATION_CHOICES: { value: 7 | 14 | 30; label: string }[] = [
  { value: 7, label: "1 week" },
  { value: 14, label: "2 weeks" },
  { value: 30, label: "1 month" },
];

const KIND_ICON: Record<
  BundlePieceKind,
  React.ComponentType<{ className?: string }>
> = {
  campaign: CalendarDays,
  content: FileTextIcon,
  ad: Megaphone,
  visual: ImageIcon,
};

const STUDIO_HREF: Record<BundlePieceKind, string> = {
  campaign: "/campaigns",
  content: "/content",
  ad: "/ads",
  visual: "/visuals",
};

export function BundleStudio() {
  const ctx = useGenerationContext();
  const [form, setForm] = useState<FormState>(DEFAULTS);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CampaignBundle | null>(null);
  const [recent, setRecent] = useState<CampaignBundle[]>([]);
  const [contextApplied, setContextApplied] = useState(false);

  const loadRecent = useCallback(async () => {
    try {
      const items = await api.bundles.list(10);
      setRecent(items);
    } catch {
      /* non-fatal */
    }
  }, []);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  // Pre-fill landing_page_id from AI context.
  useEffect(() => {
    if (contextApplied || ctx.context === null) return;
    setForm((f) => ({
      ...f,
      landing_page_id:
        f.landing_page_id ?? ctx.context!.preferences.suggested_landing_page_id,
      // Friendly default theme suggestion based on primary goal.
      theme:
        f.theme || (ctx.context!.primary_goal_text ?? f.theme),
    }));
    setContextApplied(true);
  }, [ctx.context, contextApplied]);

  const onGenerate = async () => {
    setError(null);
    setGenerating(true);
    try {
      const payload: GenerateBundlePayload = {
        theme: form.theme.trim(),
        objective: form.objective,
        duration_days: form.duration_days,
        landing_page_id: form.landing_page_id ?? undefined,
      };
      const bundle = await api.bundles.generate(payload);
      setResult(bundle);
      void loadRecent();
    } catch (e) {
      setError(
        e instanceof Error
          ? friendlyBundleError(e.message)
          : "Couldn't build the bundle.",
      );
    } finally {
      setGenerating(false);
    }
  };

  const canSubmit = !generating && form.theme.trim().length >= 2;

  if (ctx.state.kind === "missing") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Finish business onboarding first</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Bundles use your profile to keep every asset on-brand.
          </p>
          <Button asChild>
            <Link href={"/onboarding/profile" as never}>Open onboarding</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-6">
        {/* The "make a bundle" card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4 text-primary" />
              Build a coordinated campaign
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Tell us the theme + objective. We&apos;ll generate a calendar,
              two posts, an ad, and a creative brief — all sharing your
              brand voice and pointing at the same lead page.
            </p>
          </CardHeader>
          <CardContent className="space-y-5">
            <section className="space-y-2">
              <Label htmlFor="bundle-theme">Campaign theme</Label>
              <Input
                id="bundle-theme"
                value={form.theme}
                onChange={(e) =>
                  setForm((f) => ({ ...f, theme: e.target.value }))
                }
                placeholder="e.g. May launch of our chocolate Brookie bar"
                maxLength={255}
              />
            </section>

            <section className="space-y-2">
              <Label>What do you want this campaign to do?</Label>
              <div className="flex flex-wrap gap-2">
                {OBJECTIVES.map((o) => {
                  const active = form.objective === o.value;
                  return (
                    <button
                      key={o.value}
                      type="button"
                      onClick={() =>
                        setForm((f) => ({ ...f, objective: o.value }))
                      }
                      className={cn(
                        "rounded-md border px-3 py-1.5 text-left transition-colors",
                        active
                          ? "border-primary bg-accent"
                          : "border-input hover:bg-accent",
                      )}
                    >
                      <div className="text-sm font-medium">{o.label}</div>
                      <div className="text-[10px] text-muted-foreground">
                        {o.hint}
                      </div>
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="space-y-2">
              <Label>How long?</Label>
              <div className="flex flex-wrap gap-2">
                {DURATION_CHOICES.map((d) => {
                  const active = form.duration_days === d.value;
                  return (
                    <button
                      key={d.value}
                      type="button"
                      onClick={() =>
                        setForm((f) => ({ ...f, duration_days: d.value }))
                      }
                      className={cn(
                        "rounded-md border px-3 py-1.5 text-sm transition-colors",
                        active
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-input hover:bg-accent",
                      )}
                    >
                      {d.label}
                    </button>
                  );
                })}
              </div>
            </section>

            <LandingPagePicker
              value={form.landing_page_id}
              onChange={(id) =>
                setForm((f) => ({ ...f, landing_page_id: id }))
              }
              helperText="Every asset in the bundle will share this lead page — so every click across the campaign is tracked back to the same place."
            />

            <div className="flex justify-end">
              <Button
                onClick={onGenerate}
                disabled={!canSubmit}
                className="min-w-[180px]"
              >
                {generating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Building (~15s)…
                  </>
                ) : (
                  <>
                    <Package className="h-4 w-4" />
                    Build the bundle
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {error && (
          <Card>
            <CardContent className="pt-6 text-sm text-destructive">
              {error}
            </CardContent>
          </Card>
        )}

        {result && <BundleDetail bundle={result} />}
      </div>

      <RecentBundles
        items={recent}
        activeId={result?.id}
        onSelect={setResult}
      />
    </div>
  );
}

// ---------------- subcomponents ----------------

function BundleDetail({ bundle }: { bundle: CampaignBundle }) {
  const errorCount = bundle.pieces.filter((p) => p.is_error).length;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          <Package className="h-3.5 w-3.5" />
          Bundle
          <span>·</span>
          <span>{bundle.objective}</span>
          <span>·</span>
          <span>{bundle.duration_days} days</span>
        </div>
        <CardTitle className="mt-1 text-base">{bundle.theme}</CardTitle>
        {errorCount > 0 && (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-300">
            <AlertCircle className="h-3.5 w-3.5" />
            {errorCount} piece{errorCount > 1 ? "s" : ""} failed — the others
            shipped. Regenerate the failed pieces from their studio.
          </p>
        )}
      </CardHeader>
      <CardContent>
        <div className="grid gap-2">
          {bundle.pieces.map((piece, i) => (
            <PieceRow key={i} piece={piece} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function PieceRow({ piece }: { piece: BundlePiece }) {
  const Icon = KIND_ICON[piece.kind];
  const href = STUDIO_HREF[piece.kind];

  if (piece.is_error) {
    return (
      <div className="grid grid-cols-[40px_1fr_auto] items-center gap-3 rounded-md border border-amber-300/40 bg-amber-50/40 px-3 py-2.5 dark:bg-amber-950/20">
        <AlertCircle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
        <div className="min-w-0">
          <div className="text-sm font-medium">{piece.label}</div>
          <p className="text-xs text-amber-800/80 dark:text-amber-300/80">
            {piece.error_message ?? "Couldn't generate this piece."}
          </p>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link href={href as never}>
            Regenerate
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-[40px_1fr_auto] items-center gap-3 rounded-md border bg-card px-3 py-2.5">
      <div className="flex h-7 w-7 items-center justify-center rounded-md bg-muted">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Check className="h-3.5 w-3.5 text-emerald-600" />
          <div className="text-sm font-medium">{piece.label}</div>
        </div>
        {piece.subtype && (
          <p className="text-[11px] text-muted-foreground">
            {piece.subtype.replace(/_/g, " ")}
            {piece.platform ? ` · ${piece.platform}` : ""}
          </p>
        )}
      </div>
      <Button asChild size="sm" variant="outline">
        <Link href={href as never}>
          Open
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </Button>
    </div>
  );
}

function RecentBundles({
  items,
  activeId,
  onSelect,
}: {
  items: CampaignBundle[];
  activeId?: string;
  onSelect: (b: CampaignBundle) => void;
}) {
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="text-base">Recent bundles</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {items.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Your bundles will appear here.
          </p>
        )}
        {items.map((b) => {
          const active = b.id === activeId;
          const failed = b.pieces.filter((p) => p.is_error).length;
          return (
            <button
              key={b.id}
              type="button"
              onClick={() => onSelect(b)}
              className={cn(
                "w-full rounded-md border px-3 py-2 text-left transition-colors",
                active
                  ? "border-primary bg-accent"
                  : "border-transparent hover:bg-accent",
              )}
            >
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {b.objective} · {b.duration_days}d
              </div>
              <div className="mt-0.5 truncate text-sm font-medium">
                {b.theme}
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                <span>{b.pieces.length} pieces</span>
                {failed > 0 && (
                  <span className="text-amber-600 dark:text-amber-400">
                    · {failed} failed
                  </span>
                )}
                <span>· {new Date(b.created_at).toLocaleDateString()}</span>
              </div>
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}

// ---------------- helpers ----------------

function friendlyBundleError(raw: string): string {
  const lowered = raw.toLowerCase();
  if (lowered.includes("onboarding")) {
    return "Finish business onboarding before building a bundle.";
  }
  if (lowered.includes("preferred platform")) {
    return "Pick at least one preferred platform in your profile so we know where to publish.";
  }
  if (lowered.includes("503") || lowered.includes("unavailable")) {
    return "The AI was under heavy load. Try again in a moment.";
  }
  return "Couldn't build the bundle. Try again — most errors here are transient.";
}
