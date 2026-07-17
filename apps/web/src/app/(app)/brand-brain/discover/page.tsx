"use client";

/**
 * Intelligent Onboarding — AI business discovery.
 *
 * Three ways in: a real website read (the AI fetches + understands it), a
 * six-question start-from-scratch, or connecting social accounts (needs the
 * account connections, so it's honestly marked unavailable rather than faked).
 *
 * The timeline reflects the backend's REAL `stage` marker — no fake timers.
 * Nothing is saved until the owner reviews the draft and approves it.
 */

import {
  ArrowLeft,
  Brain,
  Check,
  Globe,
  Loader2,
  Rocket,
  Share2,
  Sparkles,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionHeading } from "@/components/ui/section-heading";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type DiscoveryDraft,
  type DiscoveryRun,
  type DiscoveryStage,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import { ChipsField, ColorsField, Field } from "../_components/field-editors";

export const dynamic = "force-dynamic";

type Phase = "pick" | "website" | "scratch" | "running" | "review";

const STYLES = [
  "Friendly",
  "Professional",
  "Luxury",
  "Premium",
  "Funny",
  "Bold",
  "Minimal",
  "Educational",
  "Modern",
];

const GOALS = [
  "Generate Leads",
  "Increase Sales",
  "Build Brand",
  "Grow Followers",
  "Launch Product",
  "Increase Website Traffic",
];

const STAGE_ORDER: DiscoveryStage[] = [
  "queued",
  "reading",
  "understanding",
  "building",
  "done",
];

export default function DiscoverPage() {
  const router = useRouter();
  const tenant = useTenant();
  const canSetup = tenant.can("settings.manage");

  const [phase, setPhase] = useState<Phase>("pick");
  const [run, setRun] = useState<DiscoveryRun | null>(null);
  const [draft, setDraft] = useState<DiscoveryDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Website form.
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [industry, setIndustry] = useState("");
  // Scratch form.
  const [sell, setSell] = useState("");
  const [reach, setReach] = useState("");
  const [different, setDifferent] = useState("");
  const [style, setStyle] = useState("Friendly");
  const [goal, setGoal] = useState("Generate Leads");

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const startPolling = useCallback(
    (id: string) => {
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const r = await api.discovery.get(id);
          setRun(r);
          if (r.status === "completed" && r.draft) {
            stopPolling();
            setDraft(r.draft);
            setPhase("review");
          } else if (r.status === "failed") {
            stopPolling();
            setError(r.error ?? "We couldn't finish. Please try again.");
          }
        } catch {
          /* transient — keep polling */
        }
      }, 2000);
    },
    [stopPolling],
  );

  const startWebsite = async () => {
    setBusy(true);
    setError(null);
    try {
      const { id } = await api.discovery.startWebsite({
        business_name: name.trim(),
        website_url: url.trim(),
        industry: industry.trim(),
      });
      setPhase("running");
      setRun(null);
      startPolling(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const startScratch = async () => {
    setBusy(true);
    setError(null);
    try {
      const { id } = await api.discovery.startScratch({
        business_name: name.trim(),
        what_you_sell: sell.trim(),
        who_to_reach: reach.trim(),
        what_makes_different: different.trim(),
        style,
        main_goal: goal,
        industry: industry.trim() || undefined,
      });
      setPhase("running");
      setRun(null);
      startPolling(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const applyDraft = async () => {
    if (!run || !draft) return;
    setBusy(true);
    setError(null);
    try {
      await api.discovery.apply(run.id, {
        draft,
        business_name: name.trim() || undefined,
        industry: industry.trim() || undefined,
        website: url.trim() || undefined,
      });
      router.push("/brand-brain");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save. Try again.");
      setBusy(false);
    }
  };

  if (!canSetup) {
    return (
      <EmptyState
        icon={Brain}
        title="Ask an admin to set this up"
        description="You need permission to change your workspace settings before the AI can learn about your business."
      />
    );
  }

  const setD = <K extends keyof DiscoveryDraft>(k: K, v: DiscoveryDraft[K]) =>
    setDraft((d) => (d ? { ...d, [k]: v } : d));

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6" data-testid="discover">
      {phase !== "pick" && phase !== "review" && (
        <button
          type="button"
          onClick={() => {
            stopPolling();
            setPhase("pick");
            setError(null);
          }}
          className="flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </button>
      )}

      {error && (
        <p className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad-soft-foreground">
          {error}
        </p>
      )}

      {phase === "pick" && (
        <>
          <SectionHeading
            eyebrow="Let's get started"
            heading="Tell us about your business"
            description="Pick whichever is easiest. We'll do the rest and show you what we found — you just check we got it right."
            size="lg"
          />
          <div className="grid gap-3 sm:grid-cols-3">
            <OptionCard
              icon={Globe}
              title="I have a website"
              blurb="We'll read it and learn your products, customers and brand."
              badge="Fastest"
              onClick={() => setPhase("website")}
            />
            <OptionCard
              icon={Rocket}
              title="I'm starting fresh"
              blurb="Answer 5 quick questions and we'll build your brand from scratch."
              onClick={() => setPhase("scratch")}
            />
            <OptionCard
              icon={Share2}
              title="I only have social"
              blurb="Learning from your social accounts needs them connected first."
              disabled
              disabledNote="Connect accounts in Settings → Integrations"
            />
          </div>
        </>
      )}

      {phase === "website" && (
        <>
          <SectionHeading
            eyebrow="Your website"
            heading="Where can we find you?"
            description="That's all we need. We'll read your site and figure out the rest."
            size="lg"
          />
          <div className="flex flex-col gap-4 rounded-xl border border-border p-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="d-name">Business name</Label>
              <Input
                id="d-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Bella's Bakery"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="d-url">Website address</Label>
              <Input
                id="d-url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="bellasbakery.com"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="d-ind">What kind of business is it?</Label>
              <Input
                id="d-ind"
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                placeholder="Bakery"
              />
            </div>
            <Button
              onClick={startWebsite}
              disabled={busy || !name.trim() || !url.trim() || !industry.trim()}
            >
              <Sparkles className="mr-1.5 h-4 w-4" />
              {busy ? "Starting…" : "Learn about my business"}
            </Button>
          </div>
        </>
      )}

      {phase === "scratch" && (
        <>
          <SectionHeading
            eyebrow="Starting fresh"
            heading="Five quick questions"
            description="Answer in your own words — no marketing knowledge needed."
            size="lg"
          />
          <div className="flex flex-col gap-4 rounded-xl border border-border p-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="s-name">What's your business called?</Label>
              <Input id="s-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="s-sell">What do you sell?</Label>
              <Textarea
                id="s-sell"
                rows={2}
                value={sell}
                onChange={(e) => setSell(e.target.value)}
                placeholder="Fresh sourdough bread and pastries, baked daily"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="s-reach">Who do you want to reach?</Label>
              <Textarea
                id="s-reach"
                rows={2}
                value={reach}
                onChange={(e) => setReach(e.target.value)}
                placeholder="Local families and office workers nearby"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="s-diff">What makes you different?</Label>
              <Textarea
                id="s-diff"
                rows={2}
                value={different}
                onChange={(e) => setDifferent(e.target.value)}
                placeholder="Everything is baked the same morning it's sold"
              />
            </div>
            <Picker label="Pick your style" options={STYLES} value={style} onChange={setStyle} />
            <Picker label="What's your main goal?" options={GOALS} value={goal} onChange={setGoal} />
            <Button
              onClick={startScratch}
              disabled={busy || !name.trim() || !sell.trim() || !reach.trim()}
            >
              <Sparkles className="mr-1.5 h-4 w-4" />
              {busy ? "Starting…" : "Build my brand"}
            </Button>
          </div>
        </>
      )}

      {phase === "running" && <Timeline run={run} />}

      {phase === "review" && draft && (
        <>
          <SectionHeading
            eyebrow="Here's what we found"
            heading="We've learned about your business"
            description="Have a quick read. Change anything that isn't right — then we'll save it as your Brand Brain."
            size="lg"
          />

          {draft.summary && (
            <div className="rounded-xl border border-ai-border bg-ai-soft p-4">
              <p className="whitespace-pre-wrap text-sm text-ai-soft-foreground">
                {draft.summary}
              </p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Score label="Brand" value={draft.brand_completeness_score} />
            <Score label="Content" value={draft.content_readiness_score} />
            <Score label="Ads" value={draft.advertising_readiness_score} />
            <Score label="Search" value={draft.seo_readiness_score} />
          </div>

          <Card title="Your business">
            <Field label="What you do" editing value={draft.business_description} multiline>
              <Textarea
                rows={3}
                value={draft.business_description}
                onChange={(e) => setD("business_description", e.target.value)}
              />
            </Field>
            <ChipsField label="Products" editing values={draft.products} onChange={(v) => setD("products", v)} placeholder="Add a product" />
            <ChipsField label="Services" editing values={draft.services} onChange={(v) => setD("services", v)} placeholder="Add a service" />
            <ChipsField label="What makes you different" editing values={draft.unique_selling_points} onChange={(v) => setD("unique_selling_points", v)} placeholder="Add one" />
          </Card>

          <Card title="Your customers">
            <Field label="Who you're for" editing value={draft.target_audience} multiline>
              <Textarea
                rows={3}
                value={draft.target_audience}
                onChange={(e) => setD("target_audience", e.target.value)}
              />
            </Field>
            <ChipsField label="Who else does this" editing values={draft.competitors} onChange={(v) => setD("competitors", v)} placeholder="Add a competitor" />
          </Card>

          <Card title="Your voice & look">
            <Field label="How you sound" editing value={draft.brand_tone}>
              <Input value={draft.brand_tone} onChange={(e) => setD("brand_tone", e.target.value)} />
            </Field>
            <Field label="How you write" editing value={draft.writing_style} multiline>
              <Textarea rows={2} value={draft.writing_style} onChange={(e) => setD("writing_style", e.target.value)} />
            </Field>
            <ColorsField label="Your colours" editing values={draft.brand_colors} onChange={(v) => setD("brand_colors", v)} />
            <ChipsField label="Your fonts" editing values={draft.fonts} onChange={(v) => setD("fonts", v)} placeholder="Add a font" />
          </Card>

          <Card title="Goals & words customers search">
            <ChipsField label="Goals" editing values={draft.goals} onChange={(v) => setD("goals", v)} placeholder="Add a goal" />
            <ChipsField label="Words customers search for" editing values={draft.keywords} onChange={(v) => setD("keywords", v)} placeholder="Add a word" />
            <ChipsField label="Rules we must always follow" editing values={draft.brand_rules} onChange={(v) => setD("brand_rules", v)} placeholder="e.g. Never say 'cheap'" />
          </Card>

          {(draft.content_opportunities.length > 0 ||
            draft.marketing_opportunities.length > 0 ||
            draft.seo_opportunities.length > 0) && (
            <Card title="Where we think you can grow">
              <Bullets title="Content ideas" items={draft.content_opportunities} />
              <Bullets title="Marketing ideas" items={draft.marketing_opportunities} />
              <Bullets title="Getting found online" items={draft.seo_opportunities} />
            </Card>
          )}

          <div className="sticky bottom-4 flex justify-end gap-2 rounded-xl border border-border bg-background/95 p-3 backdrop-blur">
            <Button variant="ghost" onClick={() => setPhase("pick")} disabled={busy}>
              Start over
            </Button>
            <Button onClick={applyDraft} disabled={busy} data-testid="apply-draft">
              <Check className="mr-1.5 h-4 w-4" />
              {busy ? "Saving…" : "Looks right — save it"}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------

function OptionCard({
  icon: Icon,
  title,
  blurb,
  badge,
  onClick,
  disabled,
  disabledNote,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  blurb: string;
  badge?: string;
  onClick?: () => void;
  disabled?: boolean;
  disabledNote?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex flex-col items-start gap-2 rounded-xl border p-4 text-left transition-all",
        disabled
          ? "cursor-not-allowed border-border opacity-60"
          : "border-border hover:border-ai-border hover:bg-ai-soft/40 hover:shadow-sm",
      )}
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        <Icon className="h-4.5 w-4.5" />
      </span>
      <span className="flex items-center gap-1.5 text-sm font-semibold">
        {title}
        {badge && (
          <span className="rounded-full bg-good-soft px-1.5 py-0.5 text-[10px] font-medium text-good-soft-foreground">
            {badge}
          </span>
        )}
      </span>
      <span className="text-xs text-muted-foreground">{blurb}</span>
      {disabled && disabledNote && (
        <span className="text-[11px] text-muted-foreground/70">{disabledNote}</span>
      )}
    </button>
  );
}

function Picker({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => (
          <button
            key={o}
            type="button"
            onClick={() => onChange(o)}
            aria-pressed={value === o}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              value === o
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:bg-muted",
            )}
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Timeline driven by the backend's real `stage` — never a fake timer. */
function Timeline({ run }: { run: DiscoveryRun | null }) {
  const stage: DiscoveryStage = run?.stage ?? "queued";
  const isScratch = run?.source === "scratch";
  const steps: { key: DiscoveryStage; label: string }[] = isScratch
    ? [
        { key: "queued", label: "Getting ready" },
        { key: "building", label: "Building your Brand Brain" },
      ]
    : [
        { key: "queued", label: "Getting ready" },
        { key: "reading", label: "Reading your website" },
        { key: "understanding", label: "Finding your products and customers" },
        { key: "building", label: "Building your Brand Brain" },
      ];
  const current = STAGE_ORDER.indexOf(stage);

  return (
    <div className="flex flex-col gap-6 py-8">
      <SectionHeading
        eyebrow="One moment"
        heading="We're learning about your business"
        description="This usually takes under a minute. You'll get to check everything before we save it."
        size="lg"
      />
      <ol className="flex flex-col gap-3">
        {steps.map((s) => {
          const idx = STAGE_ORDER.indexOf(s.key);
          const done = current > idx;
          const active = current === idx;
          return (
            <li key={s.key} className="flex items-center gap-3">
              <span
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full border",
                  done && "border-good bg-good text-white",
                  active && "border-ai text-ai",
                  !done && !active && "border-border text-muted-foreground/40",
                )}
              >
                {done ? (
                  <Check className="h-3.5 w-3.5" />
                ) : active ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : null}
              </span>
              <span
                className={cn(
                  "text-sm",
                  done && "text-muted-foreground",
                  active && "font-medium",
                  !done && !active && "text-muted-foreground/50",
                )}
              >
                {s.label}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border p-4">
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}

function Score({ label, value }: { label: string; value: number }) {
  const tone = value >= 70 ? "bg-good" : value >= 40 ? "bg-watch" : "bg-bad";
  return (
    <div className="rounded-lg border border-border p-2.5">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold">{value}%</p>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function Bullets({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-muted-foreground">{title}</p>
      <ul className="flex list-disc flex-col gap-1 pl-4 text-sm">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  );
}
