"use client";

/**
 * "What DM Tool believes" — a read-only window into the AI marketer's
 * evidence-backed belief memory.
 *
 * The framing matters (Constitution: never show a claim as a fact). Every item
 * here is an *evidence-backed belief*, not a certainty: it carries what DM Tool
 * concluded, why, how confident it is today (freshness-adjusted), when it was
 * established, and the evidence behind it. Beliefs that changed (were superseded
 * or contradicted) are kept — surfaced on request — so the founder can see how
 * the AI's thinking evolved, never a silent rewrite of history.
 *
 * Pure read surface: it renders GET /api/v1/beliefs. There is no write path.
 */

import { Brain, Clock, History, Lightbulb, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { BackLink } from "@/components/ui/back-link";
import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonLines } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { api, type BeliefCard } from "@/lib/api";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

const STATUS_TONE: Record<string, PillTone> = {
  active: "good",
  superseded: "muted",
  contradicted: "bad",
  unvalidated: "watch",
  retired: "muted",
};

const STATUS_LABEL: Record<string, string> = {
  active: "Currently held",
  superseded: "Replaced by a newer belief",
  contradicted: "Contradicted by later evidence",
  unvalidated: "Not yet validated",
  retired: "Retired",
};

function humanScope(scope: Record<string, string>): string {
  const parts = Object.entries(scope)
    .filter(([k]) => k !== "measured_via")
    .slice(0, 5)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${String(v).replace(/_/g, " ")}`);
  return parts.join(" · ");
}

function whenText(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function BeliefsPage() {
  const [active, setActive] = useState<BeliefCard[] | null>(null);
  const [historical, setHistorical] = useState<BeliefCard[] | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.beliefs
      .list()
      .then((res) => {
        if (!alive) return;
        setActive(res.active);
        setError(false);
      })
      .catch(() => {
        if (alive) setError(true);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const loadHistory = useCallback(() => {
    if (historical !== null) {
      setShowHistory((s) => !s);
      return;
    }
    setHistoryLoading(true);
    api.beliefs
      .list({ includeHistory: true })
      .then((res) => {
        setHistorical(res.historical);
        setShowHistory(true);
      })
      .catch(() => setHistorical([]))
      .finally(() => setHistoryLoading(false));
  }, [historical]);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6" data-testid="beliefs">
      <div className="flex flex-col gap-2">
        <BackLink href="/ai-employee" label="Your AI Marketer" />
        <SectionHeading
          eyebrow="What I've learned"
          heading="What DM Tool believes"
          description="These are evidence-backed beliefs — not fixed facts. Each one is what I've concluded from your data, how sure I am today, and the evidence behind it. As new results come in, beliefs get stronger, weaker, or replaced."
          size="lg"
        />
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-good" />
          Beliefs are formed by me from your own results. They are never edited
          away — when one changes, the old one is kept in history.
        </p>
      </div>

      {loading && (
        <div className="flex flex-col gap-4" data-testid="beliefs-loading">
          <SkeletonLines lines={3} />
          <SkeletonLines lines={3} />
        </div>
      )}

      {!loading && error && (
        <EmptyState
          icon={Brain}
          title="I couldn't load my beliefs right now"
          description="This is a read-only view of what I've learned. Give it a moment and refresh — nothing was changed."
        />
      )}

      {!loading && !error && active && active.length === 0 && (
        <EmptyState
          icon={Lightbulb}
          title="I don't hold any firm beliefs yet"
          description="Once I've watched your marketing results for a while, I'll start forming evidence-backed beliefs about what works for your business — and show them here."
          action={
            <Link
              href={"/ai-employee" as never}
              className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              See what I'm working on
            </Link>
          }
        />
      )}

      {!loading && !error && active && active.length > 0 && (
        <ul className="flex flex-col gap-4" data-testid="beliefs-active">
          {active.map((b) => (
            <BeliefItem key={b.id} belief={b} />
          ))}
        </ul>
      )}

      {!loading && !error && active && (
        <div className="flex flex-col gap-4 border-t border-border pt-5">
          <button
            type="button"
            onClick={loadHistory}
            disabled={historyLoading}
            data-testid="beliefs-history-toggle"
            className="inline-flex w-fit items-center gap-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-60"
          >
            <History className="h-4 w-4" />
            {historyLoading
              ? "Loading history…"
              : showHistory
                ? "Hide beliefs that changed"
                : "Show beliefs that changed"}
          </button>

          {showHistory && historical && historical.length === 0 && (
            <p className="text-sm text-muted-foreground">
              None of my beliefs have changed yet — nothing has been superseded
              or contradicted.
            </p>
          )}

          {showHistory && historical && historical.length > 0 && (
            <ul className="flex flex-col gap-4" data-testid="beliefs-historical">
              {historical.map((b) => (
                <BeliefItem key={b.id} belief={b} historical />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function BeliefItem({
  belief,
  historical = false,
}: {
  belief: BeliefCard;
  historical?: boolean;
}) {
  const tone = STATUS_TONE[belief.status] ?? "neutral";
  const scope = humanScope(belief.scope);
  const decayed = belief.confidence < belief.original_confidence;

  return (
    <li
      className={cn(
        "rounded-xl border border-border bg-card p-4",
        historical && "opacity-80",
      )}
      data-testid="belief-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            {belief.category}
          </span>
          <p className="text-sm font-medium leading-snug">{belief.statement}</p>
        </div>
        <StatusPill tone={tone}>{STATUS_LABEL[belief.status] ?? belief.status}</StatusPill>
      </div>

      {scope && (
        <p className="mt-2 text-xs text-muted-foreground">Where this applies — {scope}</p>
      )}

      <div className="mt-3 max-w-xs">
        <ConfidenceBar value={belief.confidence} size="lg" />
      </div>

      <div className="mt-2 flex flex-col gap-1 text-xs text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">Why:</span>{" "}
          {belief.confidence_reason}
        </p>
        {decayed && belief.freshness_reason && (
          <p className="flex items-start gap-1.5">
            <Clock className="mt-0.5 h-3 w-3 shrink-0" />
            <span>{belief.freshness_reason}</span>
          </p>
        )}
        <p>
          <span className="font-medium text-foreground">Evidence:</span>{" "}
          {belief.evidence_count === 1
            ? "1 signal"
            : `${belief.evidence_count} signals`}{" "}
          from your results
          {belief.last_validated_at
            ? ` · last confirmed ${whenText(belief.last_validated_at)}`
            : ""}
        </p>
        <p>
          <span className="font-medium text-foreground">Since:</span>{" "}
          {whenText(belief.established_at)}
        </p>
      </div>
    </li>
  );
}
