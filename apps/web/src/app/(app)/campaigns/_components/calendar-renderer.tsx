"use client";

import { Check, Copy, Link2, Megaphone } from "lucide-react";
import { useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import type {
  CalendarDay,
  CampaignSequencePhase,
} from "@/lib/api";
import { CONTENT_SUBTYPE_LABEL, prettifyEnum } from "@/lib/humanize";
import { cn } from "@/lib/utils";

/** Groups days into the funnel phases the AI returned, parsing the
 * `day_range` strings (e.g. "Days 1-3", "Day 14"). Days that don't match
 * any phase fall into a synthetic "Unphased" bucket. */
function groupDaysByPhase(
  days: CalendarDay[],
  sequence: CampaignSequencePhase[],
): Array<{ phase: CampaignSequencePhase | null; days: CalendarDay[] }> {
  const phaseRanges = sequence.map((p) => ({
    phase: p,
    range: parseDayRange(p.day_range),
  }));
  const grouped = sequence.map((p) => ({
    phase: p as CampaignSequencePhase | null,
    days: [] as CalendarDay[],
  }));
  const unphased: CalendarDay[] = [];
  for (const day of days) {
    const idx = phaseRanges.findIndex(
      ({ range }) => day.day >= range.start && day.day <= range.end,
    );
    if (idx === -1) {
      unphased.push(day);
    } else {
      grouped[idx].days.push(day);
    }
  }
  if (unphased.length) {
    grouped.push({ phase: null, days: unphased });
  }
  return grouped.filter((g) => g.days.length > 0);
}

function parseDayRange(raw: string): { start: number; end: number } {
  const nums = Array.from(raw.matchAll(/\d+/g)).map((m) => Number(m[0]));
  if (nums.length === 0) return { start: 0, end: 0 };
  if (nums.length === 1) return { start: nums[0], end: nums[0] };
  return { start: Math.min(...nums), end: Math.max(...nums) };
}

export function CalendarRenderer({
  days,
  sequence,
  shareUrls,
}: {
  days: CalendarDay[];
  sequence: CampaignSequencePhase[];
  /** Map of day number string → attributed share URL.
   *  Empty when no landing page is attached. */
  shareUrls?: Record<string, string>;
}) {
  const groups = groupDaysByPhase(days, sequence);

  return (
    <div className="space-y-6">
      {groups.map((g, i) => (
        <div key={i} className="space-y-2">
          {g.phase ? <PhaseHeader phase={g.phase} /> : <UnphasedHeader />}
          <div className="grid gap-2">
            {g.days.map((d) => (
              <DayCard
                key={d.day}
                day={d}
                shareUrl={shareUrls?.[String(d.day)] ?? null}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function PhaseHeader({ phase }: { phase: CampaignSequencePhase }) {
  return (
    <div className="rounded-md border border-border bg-card px-3 py-2">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {phase.day_range}
        </span>
        <h3 className="text-sm font-semibold">{phase.phase_name}</h3>
        <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          metric · {phase.primary_metric}
        </span>
      </div>
      <p className="mt-0.5 text-xs text-muted-foreground">{phase.objective}</p>
    </div>
  );
}

function UnphasedHeader() {
  return (
    <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
      Unphased
    </div>
  );
}

function DayCard({
  day,
  shareUrl,
}: {
  day: CalendarDay;
  shareUrl: string | null;
}) {
  const hasAd =
    day.recommended_ad_support &&
    day.recommended_ad_support.toLowerCase() !== "none";

  return (
    <Card>
      <CardContent className="grid gap-3 pt-4 sm:grid-cols-[72px_1fr]">
        <div className="flex flex-col items-center justify-start">
          <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Day
          </div>
          <div className="text-2xl font-semibold tabular-nums leading-none">
            {day.day}
          </div>
        </div>
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
            <Pill emphasised>{day.platform}</Pill>
            <Pill>{CONTENT_SUBTYPE_LABEL[day.content_type] ?? prettifyEnum(day.content_type)}</Pill>
            <Pill>{day.objective}</Pill>
            {hasAd && (
              <span className="ml-auto flex items-center gap-1 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                <Megaphone className="h-3 w-3" />
                Boost
              </span>
            )}
          </div>
          <div>
            <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Hook
            </div>
            <p className="text-sm font-medium leading-snug">{day.hook}</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <Section label="CTA" body={day.cta} />
            <Section label="Why this slot" body={day.rationale} muted />
          </div>
          {shareUrl && <DayShareUrl url={shareUrl} day={day.day} />}
          <details className="group">
            <summary className="cursor-pointer text-[11px] font-medium text-muted-foreground hover:text-foreground">
              Visual direction summary
            </summary>
            <p className="mt-1 text-xs text-muted-foreground">
              {day.visual_direction_summary}
            </p>
          </details>
          {hasAd && (
            <details className="group">
              <summary className="cursor-pointer text-[11px] font-medium text-muted-foreground hover:text-foreground">
                Ad support recommendation
              </summary>
              <p className="mt-1 text-xs text-muted-foreground">
                {day.recommended_ad_support}
              </p>
            </details>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function DayShareUrl({ url, day }: { url: string; day: number }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <div className="flex items-center gap-2 rounded-md border border-dashed bg-muted/30 px-2 py-1.5">
      <Link2 className="h-3 w-3 shrink-0 text-muted-foreground" />
      <code className="flex-1 truncate text-[11px] text-muted-foreground">
        {url}
      </code>
      <button
        type="button"
        onClick={onCopy}
        className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium hover:bg-accent"
        title={`Copy day ${day} share link`}
      >
        {copied ? (
          <Check className="h-3 w-3" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function Section({
  label,
  body,
  muted,
}: {
  label: string;
  body: string;
  muted?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <p
        className={cn(
          "text-xs leading-snug",
          muted ? "text-muted-foreground" : "text-foreground",
        )}
      >
        {body}
      </p>
    </div>
  );
}

function Pill({
  children,
  emphasised,
}: {
  children: React.ReactNode;
  emphasised?: boolean;
}) {
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 text-[10px] font-medium",
        emphasised
          ? "bg-foreground text-background"
          : "bg-muted text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}
