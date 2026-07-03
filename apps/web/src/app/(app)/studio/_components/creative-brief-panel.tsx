"use client";

/**
 * Phase 6.3 — AI Creative Brief panel.
 *
 * The bridge from Content Studio → Creative Studio: generate a creative brief
 * GROUNDED in real context (business profile + strategy + optional campaign /
 * content) via the live /creative/brief API. Nothing is fabricated — the panel
 * surfaces exactly which sources fed the brief (`grounded_in`) and the model's
 * confidence + reason. Design system reused throughout.
 */

import { FileText, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { Surface } from "@/components/ui/surface";
import { api, type GeneratedContent } from "@/lib/api";
import type { CreativeBrief } from "@/lib/studio-types";

function confidenceTone(c: number): PillTone {
  return c >= 80 ? "good" : c >= 60 ? "watch" : "bad";
}

function humanize(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function BriefView({ brief }: { brief: CreativeBrief }) {
  const d = brief.brief;
  return (
    <Surface padding="compact" className="space-y-3" data-testid="creative-brief-view">
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone={confidenceTone(brief.confidence)} size="sm">
          {brief.confidence}% confidence
        </StatusPill>
        {brief.grounded_in.map((g) => (
          <StatusPill key={g} tone="ai" size="sm">
            {humanize(g)}
          </StatusPill>
        ))}
        <span className="ml-auto text-xs text-muted-foreground">
          {new Date(brief.created_at).toLocaleString()}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Objective" value={d.objective} />
        <Field label="Audience" value={d.audience} />
        <Field label="Key message" value={d.key_message} />
        <Field label="Tone" value={d.tone} />
      </div>
      <Field label="Visual direction" value={d.visual_direction} />

      {d.deliverables.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Recommended deliverables</p>
          <div className="flex flex-wrap gap-1.5">
            {d.deliverables.map((x) => (
              <StatusPill key={x} tone="neutral" size="sm">
                {humanize(x)}
              </StatusPill>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {d.must_include.length > 0 && (
          <List label="Must include" tone="good" items={d.must_include} />
        )}
        {d.avoid.length > 0 && <List label="Avoid" tone="bad" items={d.avoid} />}
      </div>

      {brief.reason && (
        <p className="text-xs text-muted-foreground">
          <span className="font-medium">Grounding:</span> {brief.reason}
        </p>
      )}
    </Surface>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="text-sm">{value}</p>
    </div>
  );
}

function List({ label, tone, items }: { label: string; tone: PillTone; items: string[] }) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <ul className="space-y-0.5">
        {items.map((x, i) => (
          <li key={i} className="flex items-start gap-1.5 text-sm">
            <StatusPill tone={tone} size="sm" className="mt-0.5">
              {tone === "good" ? "✓" : "✕"}
            </StatusPill>
            <span>{x}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CreativeBriefPanel() {
  const [objective, setObjective] = useState("");
  const [contentId, setContentId] = useState("");
  const [content, setContent] = useState<GeneratedContent[]>([]);
  const [briefs, setBriefs] = useState<CreativeBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [b, c] = await Promise.all([
        api.studio.brief.list(),
        api.content.list({ limit: 30 }).catch(() => [] as GeneratedContent[]),
      ]);
      setBriefs(b);
      setContent(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load briefs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const generate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const brief = await api.studio.brief.generate({
        objective: objective.trim() || undefined,
        content_id: contentId || undefined,
      });
      setBriefs((prev) => [brief, ...prev]);
      setObjective("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate brief.");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="creative-brief-panel">
      <SectionHeading
        eyebrow="AI Creative Brief"
        heading="Turn strategy + content into a design brief"
        description="Grounded in your business profile, active strategy, and (optionally) a piece of content — never invented."
      />

      <Surface padding="compact" className="space-y-3">
        <label className="block space-y-1">
          <span className="text-xs font-medium text-muted-foreground">
            Objective (optional — inferred from context if blank)
          </span>
          <Input
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder="e.g. Drive weekend bookings"
            maxLength={200}
            data-testid="brief-objective"
          />
        </label>

        {content.length > 0 && (
          <label className="block space-y-1">
            <span className="text-xs font-medium text-muted-foreground">
              Ground on a content piece (optional)
            </span>
            <select
              value={contentId}
              onChange={(e) => setContentId(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              data-testid="brief-content-select"
            >
              <option value="">None</option>
              {content.map((c) => (
                <option key={c.id} value={c.id}>
                  {humanize(c.content_type)} — {c.goal.slice(0, 48)}
                </option>
              ))}
            </select>
          </label>
        )}

        <Button onClick={() => void generate()} disabled={generating} data-testid="brief-generate">
          <Sparkles className="h-4 w-4" />
          {generating ? "Generating…" : "Generate brief"}
        </Button>

        {error && (
          <Surface state="bad" padding="compact" className="text-xs text-bad">
            {error}
          </Surface>
        )}
      </Surface>

      {loading ? (
        <Skeleton className="h-40 w-full" />
      ) : briefs.length === 0 ? (
        <Surface padding="compact" className="flex items-center gap-2 text-sm text-muted-foreground">
          <FileText className="h-4 w-4" />
          No briefs yet — generate one to kick off a design.
        </Surface>
      ) : (
        <div className="space-y-3">
          {briefs.map((b) => (
            <BriefView key={b.id} brief={b} />
          ))}
        </div>
      )}
    </div>
  );
}
