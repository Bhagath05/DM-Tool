"use client";

/**
 * Brand Brain — the single source of truth every AI workflow inherits.
 *
 * Everything the platform generates (posts, ads, blogs, designs) is built
 * from this profile via the backend generation-context block. This page
 * lets the owner see and refine what the AI knows, in plain language — no
 * marketing jargon. Reads GET /business/profile; saves via
 * PUT /business/profile (gated on settings.manage server-side).
 */

import {
  Brain,
  Check,
  Palette,
  Pencil,
  Plus,
  Sparkles,
  Target,
  Type as TypeIcon,
  Users,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonLines } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, type BusinessProfile } from "@/lib/api";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

/** The editable slice of the profile the Brand Brain manages. */
interface Draft {
  business_name: string;
  website: string;
  industry: string;
  target_audience: string;
  brand_tone: string;
  writing_style: string;
  pricing: string;
  products: string[];
  services: string[];
  unique_selling_points: string[];
  competitors: string[];
  goals: string[];
  keywords: string[];
  brand_colors: string[];
  fonts: string[];
  brand_rules: string[];
}

function toDraft(p: BusinessProfile): Draft {
  return {
    business_name: p.business_name ?? "",
    website: p.website ?? "",
    industry: p.industry ?? "",
    target_audience: p.target_audience ?? "",
    brand_tone: p.brand_tone ?? "",
    writing_style: p.writing_style ?? "",
    pricing: p.pricing ?? "",
    products: p.products ?? [],
    services: p.services ?? [],
    unique_selling_points: p.unique_selling_points ?? [],
    competitors: p.competitors ?? [],
    goals: p.goals ?? [],
    keywords: p.keywords ?? [],
    brand_colors: p.brand_colors ?? [],
    fonts: p.fonts ?? [],
    brand_rules: p.brand_rules ?? [],
  };
}

export default function BrandBrainPage() {
  const tenant = useTenant();
  const canEdit = tenant.can("settings.manage");

  const [profile, setProfile] = useState<BusinessProfile | null | undefined>(
    undefined,
  );
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const p = await api.business.get();
      setProfile(p);
      if (p) setDraft(toDraft(p));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load your Brand Brain.");
      setProfile(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => (d ? { ...d, [key]: value } : d));

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.business.update({
        business_name: draft.business_name,
        website: draft.website || undefined,
        industry: draft.industry,
        target_audience: draft.target_audience,
        brand_tone: draft.brand_tone,
        writing_style: draft.writing_style || undefined,
        pricing: draft.pricing || undefined,
        products: draft.products,
        services: draft.services,
        unique_selling_points: draft.unique_selling_points,
        competitors: draft.competitors,
        goals: draft.goals,
        keywords: draft.keywords,
        brand_colors: draft.brand_colors,
        fonts: draft.fonts,
        brand_rules: draft.brand_rules,
      });
      setProfile(updated);
      setDraft(toDraft(updated));
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save your changes.");
    } finally {
      setSaving(false);
    }
  };

  const completeness = useMemo(
    () => (draft ? scoreCompleteness(draft) : 0),
    [draft],
  );

  if (profile === undefined) return <SkeletonLines lines={10} />;

  if (profile === null || !draft) {
    return (
      <EmptyState
        icon={Brain}
        title="Your Brand Brain is empty"
        description="Finish setting up your business so the AI can create on-brand marketing for you."
        action={
          <Button asChild>
            <a href="/onboarding/profile">Set up my brand</a>
          </Button>
        }
      />
    );
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6" data-testid="brand-brain">
      <SectionHeading
        eyebrow="Brand Brain"
        heading="Everything your AI marketer knows about you"
        description="Every post, ad, blog and design is built from this. The more complete and accurate it is, the more on-brand your marketing becomes."
        size="lg"
        action={
          canEdit ? (
            editing ? (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setDraft(toDraft(profile));
                    setEditing(false);
                    setError(null);
                  }}
                  disabled={saving}
                >
                  Cancel
                </Button>
                <Button size="sm" onClick={save} disabled={saving}>
                  <Check className="mr-1.5 h-3.5 w-3.5" />
                  {saving ? "Saving…" : "Save"}
                </Button>
              </div>
            ) : (
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                <Pencil className="mr-1.5 h-3.5 w-3.5" />
                Edit
              </Button>
            )
          ) : undefined
        }
      />

      <CompletenessBar score={completeness} />

      {error && (
        <p className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad-soft-foreground">
          {error}
        </p>
      )}

      {/* Business basics */}
      <Section icon={Sparkles} title="Your business" hint="Who you are and what you do.">
        <Field label="Business name" editing={editing} value={draft.business_name}>
          <Input value={draft.business_name} onChange={(e) => set("business_name", e.target.value)} />
        </Field>
        <Field label="Website" editing={editing} value={draft.website}>
          <Input value={draft.website} onChange={(e) => set("website", e.target.value)} placeholder="https://…" />
        </Field>
        <Field label="Industry" editing={editing} value={draft.industry}>
          <Input value={draft.industry} onChange={(e) => set("industry", e.target.value)} />
        </Field>
        <Field label="Pricing" editing={editing} value={draft.pricing} hint="How you price — e.g. 'Starts at ₹499/month'.">
          <Input value={draft.pricing} onChange={(e) => set("pricing", e.target.value)} />
        </Field>
      </Section>

      {/* What you sell */}
      <Section icon={Target} title="What you sell" hint="Products, services, and what makes you different.">
        <ChipsField label="Products" editing={editing} values={draft.products} onChange={(v) => set("products", v)} placeholder="Add a product" />
        <ChipsField label="Services" editing={editing} values={draft.services} onChange={(v) => set("services", v)} placeholder="Add a service" />
        <ChipsField
          label="What makes you different"
          editing={editing}
          values={draft.unique_selling_points}
          onChange={(v) => set("unique_selling_points", v)}
          placeholder="e.g. Same-day delivery"
        />
      </Section>

      {/* Audience */}
      <Section icon={Users} title="Your audience" hint="Who you're trying to reach.">
        <Field label="Target audience" editing={editing} value={draft.target_audience} multiline>
          <Textarea rows={3} value={draft.target_audience} onChange={(e) => set("target_audience", e.target.value)} />
        </Field>
        <ChipsField label="Competitors" editing={editing} values={draft.competitors} onChange={(v) => set("competitors", v)} placeholder="Add a competitor" />
      </Section>

      {/* Voice */}
      <Section icon={Pencil} title="Your voice" hint="How your brand sounds when it speaks.">
        <Field label="Brand tone" editing={editing} value={draft.brand_tone} hint="e.g. warm, playful, professional.">
          <Input value={draft.brand_tone} onChange={(e) => set("brand_tone", e.target.value)} />
        </Field>
        <Field label="Writing style" editing={editing} value={draft.writing_style} multiline hint="How sentences should feel — the AI copies this.">
          <Textarea rows={3} value={draft.writing_style} onChange={(e) => set("writing_style", e.target.value)} placeholder="e.g. Short, warm, sensory sentences. No jargon." />
        </Field>
      </Section>

      {/* Look */}
      <Section icon={Palette} title="Your look" hint="Colours and fonts every design will use.">
        <ColorsField label="Brand colours" editing={editing} values={draft.brand_colors} onChange={(v) => set("brand_colors", v)} />
        <ChipsField label="Fonts" editing={editing} values={draft.fonts} onChange={(v) => set("fonts", v)} placeholder="Add a font" icon={TypeIcon} />
      </Section>

      {/* Keywords + goals */}
      <Section icon={Target} title="Goals & keywords" hint="What you want, and the words to weave in.">
        <ChipsField label="Goals" editing={editing} values={draft.goals} onChange={(v) => set("goals", v)} placeholder="e.g. Get more bookings" />
        <ChipsField label="Keywords" editing={editing} values={draft.keywords} onChange={(v) => set("keywords", v)} placeholder="Add a keyword" />
      </Section>

      {/* Rules */}
      <Section icon={Brain} title="Brand rules" hint="Hard rules the AI must never break.">
        <ChipsField
          label="Rules"
          editing={editing}
          values={draft.brand_rules}
          onChange={(v) => set("brand_rules", v)}
          placeholder="e.g. Never use the word 'cheap'"
        />
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Pieces
// ---------------------------------------------------------------------

function Section({
  icon: Icon,
  title,
  hint,
  children,
}: {
  icon: typeof Brain;
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border bg-background p-4 sm:p-5">
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Icon className="h-4 w-4" />
        </span>
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </div>
      </div>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}

function Field({
  label,
  value,
  editing,
  multiline,
  hint,
  children,
}: {
  label: string;
  value: string;
  editing: boolean;
  multiline?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {hint && editing && <span className="text-[11px] text-muted-foreground/70">{hint}</span>}
      </div>
      {editing ? (
        children
      ) : value ? (
        <p className={cn("text-sm", multiline && "whitespace-pre-wrap")}>{value}</p>
      ) : (
        <p className="text-sm text-muted-foreground/60 italic">Not set yet</p>
      )}
    </div>
  );
}

function ChipsField({
  label,
  values,
  editing,
  onChange,
  placeholder,
  icon: Icon,
}: {
  label: string;
  values: string[];
  editing: boolean;
  onChange: (v: string[]) => void;
  placeholder?: string;
  icon?: typeof Brain;
}) {
  const [input, setInput] = useState("");
  const add = () => {
    const v = input.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setInput("");
  };
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {values.length === 0 && !editing ? (
        <p className="text-sm text-muted-foreground/60 italic">Not set yet</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {values.map((v) => (
            <span
              key={v}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs"
            >
              {Icon && <Icon className="h-3 w-3 text-muted-foreground" />}
              {v}
              {editing && (
                <button
                  type="button"
                  onClick={() => onChange(values.filter((x) => x !== v))}
                  aria-label={`Remove ${v}`}
                  className="text-muted-foreground hover:text-bad-soft-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      {editing && (
        <div className="mt-1 flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
            placeholder={placeholder}
            className="h-8 text-sm"
          />
          <Button type="button" size="sm" variant="outline" onClick={add} disabled={!input.trim()}>
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </div>
  );
}

function ColorsField({
  label,
  values,
  editing,
  onChange,
}: {
  label: string;
  values: string[];
  editing: boolean;
  onChange: (v: string[]) => void;
}) {
  const [input, setInput] = useState("#");
  const add = () => {
    const v = input.trim();
    if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(v) && !values.includes(v)) {
      onChange([...values, v]);
    }
    setInput("#");
  };
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {values.length === 0 && !editing ? (
        <p className="text-sm text-muted-foreground/60 italic">Not set yet</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {values.map((c) => (
            <span key={c} className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-1 text-xs">
              <span className="h-4 w-4 rounded-full border border-border" style={{ backgroundColor: c }} aria-hidden />
              <span className="font-mono">{c}</span>
              {editing && (
                <button
                  type="button"
                  onClick={() => onChange(values.filter((x) => x !== c))}
                  aria-label={`Remove ${c}`}
                  className="text-muted-foreground hover:text-bad-soft-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      {editing && (
        <div className="mt-1 flex items-center gap-2">
          <input
            type="color"
            value={/^#([0-9a-fA-F]{6})$/.test(input) ? input : "#000000"}
            onChange={(e) => setInput(e.target.value)}
            aria-label="Pick colour"
            className="h-8 w-10 cursor-pointer rounded border border-input bg-background"
          />
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
            placeholder="#8B4513"
            className="h-8 w-28 font-mono text-sm"
          />
          <Button type="button" size="sm" variant="outline" onClick={add}>
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </div>
  );
}

function CompletenessBar({ score }: { score: number }) {
  const tone = score >= 80 ? "good" : score >= 50 ? "watch" : "bad";
  const label =
    score >= 80
      ? "Your AI marketer has a strong picture of your brand."
      : score >= 50
        ? "Good start — fill the gaps for sharper, more on-brand results."
        : "Add more so the AI can create marketing that sounds like you.";
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-medium">Brand Brain completeness</span>
        <span className="text-muted-foreground">{score}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            tone === "good" && "bg-good",
            tone === "watch" && "bg-watch",
            tone === "bad" && "bg-bad",
          )}
          style={{ width: `${score}%` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function scoreCompleteness(d: Draft): number {
  const checks = [
    !!d.business_name,
    !!d.website,
    !!d.industry,
    !!d.target_audience,
    !!d.brand_tone,
    !!d.writing_style,
    !!d.pricing,
    d.products.length > 0,
    d.services.length > 0,
    d.unique_selling_points.length > 0,
    d.competitors.length > 0,
    d.goals.length > 0,
    d.keywords.length > 0,
    d.brand_colors.length > 0,
    d.fonts.length > 0,
    d.brand_rules.length > 0,
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}
