"use client";

/**
 * Phase 8 — One-click execution.
 *
 * `<QuickGenerateButton>` collapses the old four-step flow
 *
 *   Today → Opportunity → Content Studio → Fill form → Generate
 *
 * into a single click + a few seconds of wait:
 *
 *   Today → Generate → Result
 *
 * The button stays a single prop-driven primitive that any advisory
 * card (hero, opportunity, trend) can drop in. Clicking it opens a
 * modal that **auto-fires `api.content.generate(...)` on mount** with
 * the request derived from the card's context. The result renders
 * inline using the same `ContentRenderer` the Content Studio uses —
 * zero duplication, zero divergence.
 *
 * Constitution compliance:
 *  - Above the generated content we always render the founder
 *    Constitution headers (what's happening · why we made this ·
 *    expected result · confidence). The four questions remain
 *    answerable even before generation completes.
 *
 * Backend reuse rules (Phase 8 #4 + #5):
 *  - Reuses the existing `POST /api/v1/content/generate` endpoint.
 *  - Reuses the existing `ContentRenderer`.
 *  - No new LLM calls server-side, no new endpoints.
 *
 * Modal first, drawer not required: shadcn-style dialog rendered via
 * the in-house `<Modal>` primitive (portal + focus trap + ESC).
 */

import {
  AlertTriangle,
  ArrowRight,
  Check,
  Copy,
  ExternalLink,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import {
  ApiError,
  api,
  type ContentType,
  type GeneratedContent,
  type GenerateContentPayload,
  type Opportunity,
  type OpportunityImpactCategory,
  type TrendingTopic,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import {
  ContentRenderer,
  serializeForCopy,
} from "../app/(app)/content/_components/content-renderer";

// ----------------------------------------------------------------------
//  Types
// ----------------------------------------------------------------------

/**
 * Everything QuickGenerate needs to fire a content generation AND
 * tell the founder why we're firing it. Tightly typed so callers
 * can't surface QuickGenerate without honouring the Constitution.
 */
export interface QuickGenerateContext {
  /** Sent to `api.content.generate` verbatim — `platform` may be null
   *  to mean "use the user's primary preferred platform". */
  request: {
    content_type: ContentType;
    /** Null → drawer pulls the founder's first preferred platform. */
    platform: string | null;
    goal: string;
    tone?: string;
  };
  /** Founder-facing source attribution + Constitution context. */
  source: {
    /** Where this generate came from (e.g. "From an opportunity"). */
    label: string;
    /** One-sentence headline a non-marketer reads as "what we're making". */
    headline: string;
    /** Why this advisory exists — surfaces above the result so the
     *  generation is never a black box. */
    reason: string;
    /** Plain-language outcome the founder can hold us to. */
    expectedResult: string;
    /** 0-100. Same scale as Constitution `<AiRecommendation>`. */
    confidence: number;
  };
  /** When set, uses POST /advisor/execute instead of raw content.generate. */
  recommendationId?: string;
}

// ----------------------------------------------------------------------
//  Button
// ----------------------------------------------------------------------

export interface QuickGenerateButtonProps {
  context: QuickGenerateContext;
  className?: string;
  variant?: "default" | "outline";
  size?: "sm" | "default";
  label?: string;
  "data-testid"?: string;
}

/**
 * Single CTA — opens the modal which then auto-generates.
 *
 * The button is the public surface that cards (hero, opportunity,
 * trend) consume. Owns its own open state so each card in a list
 * can have its own independent modal without parent plumbing.
 */
export function QuickGenerateButton({
  context,
  className,
  variant = "default",
  size = "sm",
  label = "Generate now",
  "data-testid": testId = "quick-generate-button",
}: QuickGenerateButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        type="button"
        size={size}
        variant={variant}
        onClick={() => setOpen(true)}
        className={cn(className)}
        data-testid={testId}
      >
        <Sparkles className="h-3.5 w-3.5" />
        {label}
      </Button>
      <QuickGenerateModal
        open={open}
        onOpenChange={setOpen}
        context={context}
      />
    </>
  );
}

// ----------------------------------------------------------------------
//  Modal — the actual execution surface
// ----------------------------------------------------------------------

type GenState =
  | { kind: "idle" }
  | { kind: "loading"; startedAt: number }
  | {
      kind: "ready";
      result: GeneratedContent;
      contentAssetId?: string | null;
    }
  | { kind: "no-profile" }
  | { kind: "error"; message: string };

export interface QuickGenerateModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  context: QuickGenerateContext;
}

export function QuickGenerateModal({
  open,
  onOpenChange,
  context,
}: QuickGenerateModalProps) {
  const [state, setState] = useState<GenState>({ kind: "idle" });
  // Bumps each time the user clicks "Generate another" so the
  // useEffect below re-fires with the same payload.
  const [generationId, setGenerationId] = useState(0);
  // Tracks whether this open instance has already auto-fired. Prevents
  // a re-fire on every render while the modal is open.
  const lastFiredKey = useRef<string | null>(null);

  // Auto-fire as soon as the modal opens. Re-fires on `generationId`
  // bumps (the "Generate another" button) and on prop-context change
  // (rare, but defensible).
  useEffect(() => {
    if (!open) {
      // Reset on close so the next open starts fresh.
      lastFiredKey.current = null;
      return;
    }
    const key = `${generationId}:${JSON.stringify(context.request)}`;
    if (lastFiredKey.current === key) return;
    lastFiredKey.current = key;

    let cancelled = false;
    const startedAt = Date.now();
    setState({ kind: "loading", startedAt });

    void (async () => {
      try {
        if (context.recommendationId) {
          const exec = await api.advisor.execute(context.recommendationId);
          if (exec.asset_type === "content") {
            const result = await api.content.byId(exec.asset_id);
            if (cancelled) return;
            setState({
              kind: "ready",
              result,
              contentAssetId: exec.content_asset_id,
            });
            return;
          }
        }

        // Resolve platform — null means "use the founder's primary
        // preferred platform". We fetch the profile lazily here so
        // callers don't have to thread it through every advisory card.
        const platform = await resolvePlatform(context.request.platform);

        const payload: GenerateContentPayload = {
          content_type: context.request.content_type,
          platform,
          goal: context.request.goal,
          tone: context.request.tone,
        };
        const result = await api.content.generate(payload);
        if (cancelled) return;
        setState({ kind: "ready", result });
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 409) {
          setState({ kind: "no-profile" });
          return;
        }
        setState({
          kind: "error",
          message:
            e instanceof Error
              ? friendlyError(e.message)
              : "Generation failed. Try again in a moment.",
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, context, generationId]);

  const onRegenerate = useCallback(() => {
    setGenerationId((n) => n + 1);
  }, []);

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={
        <span className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          {context.source.headline}
        </span>
      }
      description={context.source.label}
      data-testid="quick-generate-modal"
      className="max-w-2xl"
    >
      <div className="space-y-4 p-5">
        <ContextStrip source={context.source} />

        {state.kind === "loading" && (
          <LoadingPanel startedAt={state.startedAt} />
        )}

        {state.kind === "ready" && (
          <ResultPanel
            context={context}
            result={state.result}
            contentAssetId={state.contentAssetId}
            onRegenerate={onRegenerate}
            onClose={() => onOpenChange(false)}
          />
        )}

        {state.kind === "no-profile" && <NoProfilePanel />}

        {state.kind === "error" && (
          <ErrorPanel
            message={state.message}
            onRetry={onRegenerate}
            context={context}
          />
        )}
      </div>
    </Modal>
  );
}

// ----------------------------------------------------------------------
//  Context strip — Constitution above the result
// ----------------------------------------------------------------------

function ContextStrip({
  source,
}: {
  source: QuickGenerateContext["source"];
}) {
  const band = confidenceBand(source.confidence);
  return (
    <section
      className="space-y-2 rounded-md border bg-muted/30 px-3 py-2.5 text-xs"
      data-testid="quick-generate-context"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium",
            band.cls,
          )}
          data-testid="quick-generate-confidence"
        >
          {band.label} ({source.confidence}%)
        </span>
        <span
          className="text-[11px] text-muted-foreground"
          data-testid="quick-generate-reason"
        >
          {source.reason}
        </span>
      </div>
      <p className="text-xs text-foreground/85">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          What to expect ·{" "}
        </span>
        {source.expectedResult}
      </p>
    </section>
  );
}

// ----------------------------------------------------------------------
//  Loading
// ----------------------------------------------------------------------

function LoadingPanel({ startedAt }: { startedAt: number }) {
  // Tick once per second so the "elapsed" hint moves. Founders see
  // visible progress instead of staring at a static spinner.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));

  return (
    <div
      className="flex items-center gap-3 rounded-md border border-dashed bg-card px-4 py-6 text-sm text-muted-foreground"
      data-testid="quick-generate-loading"
    >
      <Loader2 className="h-5 w-5 animate-spin text-primary" />
      <div className="space-y-0.5">
        <p className="font-medium text-foreground">
          Drafting your post…
        </p>
        <p className="text-xs">
          Typically 8-15 seconds. {seconds}s elapsed.
        </p>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------
//  Result
// ----------------------------------------------------------------------

function ResultPanel({
  context,
  result,
  contentAssetId,
  onRegenerate,
  onClose,
}: {
  context: QuickGenerateContext;
  result: GeneratedContent;
  contentAssetId?: string | null;
  onRegenerate: () => void;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [scheduleStatus, setScheduleStatus] = useState<string | null>(null);
  const onCopy = useCallback(async () => {
    try {
      const body = serializeForCopy(result.content_type, result.output);
      const text = result.share_url
        ? `${body}\n\n${result.share_url}`
        : body;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard API unavailable in some browsers */
    }
  }, [result]);

  const customizeHref = buildCustomizeHref(context, result);

  const schedulePlatform =
    result.platform.toLowerCase().includes("google")
      ? ("google_business_profile" as const)
      : ("instagram" as const);

  const onSchedule = async () => {
    if (!context.recommendationId) return;
    setScheduling(true);
    setScheduleStatus(null);
    try {
      const scheduled = await api.advisor.schedule({
        recommendation_id: context.recommendationId,
        platform: schedulePlatform,
        scheduled_at: new Date().toISOString(),
      });
      if (scheduled.publish_status === "published") {
        setScheduleStatus("Published — performance will sync on next platform sync.");
      } else if (scheduled.publish_status === "failed") {
        setScheduleStatus(scheduled.error_message ?? "Publish failed.");
      } else {
        setScheduleStatus(`Scheduled for ${schedulePlatform}.`);
      }
    } catch (e) {
      setScheduleStatus(e instanceof Error ? e.message : "Couldn't schedule.");
    } finally {
      setScheduling(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="quick-generate-result">
      <header className="flex flex-wrap items-center gap-2">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          What to post
        </div>
        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {prettyContentType(result.content_type)} · {result.platform}
        </span>
      </header>

      <div className="rounded-md border bg-card p-4">
        <ContentRenderer
          contentType={result.content_type}
          output={result.output}
        />
      </div>

      <footer className="flex flex-wrap items-center gap-2 border-t pt-3">
        {context.recommendationId && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={onSchedule}
            disabled={scheduling}
            data-testid="quick-generate-schedule"
          >
            {scheduling ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : null}
            Schedule & publish
          </Button>
        )}
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onCopy}
          data-testid="quick-generate-copy"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
          {copied ? "Copied" : "Copy text"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onRegenerate}
          data-testid="quick-generate-regenerate"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Generate another
        </Button>
        <Button asChild size="sm" variant="ghost">
          <Link
            href={customizeHref as never}
            prefetch={false}
            data-testid="quick-generate-customize"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Customize in studio
          </Link>
        </Button>
        <Button
          type="button"
          size="sm"
          className="ml-auto"
          onClick={onClose}
          data-testid="quick-generate-done"
        >
          Done
          <ArrowRight className="h-3.5 w-3.5" />
        </Button>
      </footer>
      {scheduleStatus && (
        <p className="text-xs text-muted-foreground">{scheduleStatus}</p>
      )}
    </section>
  );
}

// ----------------------------------------------------------------------
//  Error states
// ----------------------------------------------------------------------

function ErrorPanel({
  message,
  onRetry,
  context,
}: {
  message: string;
  onRetry: () => void;
  context: QuickGenerateContext;
}) {
  return (
    <section
      className="space-y-3 rounded-md border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-sm"
      data-testid="quick-generate-error"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" />
        <p className="text-foreground/90">{message}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          onClick={onRetry}
          data-testid="quick-generate-error-retry"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Try again
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link
            href={buildCustomizeHref(context, null) as never}
            prefetch={false}
            data-testid="quick-generate-error-customize"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Customize in studio
          </Link>
        </Button>
      </div>
    </section>
  );
}

function NoProfilePanel() {
  return (
    <section
      className="space-y-3 rounded-md border border-dashed bg-muted/30 px-4 py-3 text-sm"
      data-testid="quick-generate-no-profile"
    >
      <p className="text-foreground/90">
        Finish business onboarding first — the AI needs your industry,
        audience, and tone to draft something that sounds like you.
      </p>
      <Button asChild size="sm">
        <Link href={"/onboarding/profile" as never}>Open onboarding</Link>
      </Button>
    </section>
  );
}

// ----------------------------------------------------------------------
//  Helpers
// ----------------------------------------------------------------------

const DEFAULT_PLATFORM = "Instagram";

/**
 * Resolve a generation platform.
 *
 * If the caller passed an explicit string, use it verbatim. If they
 * passed `null`, fetch the founder's profile and pick their first
 * preferred platform. If we can't fetch (network error, etc.) we
 * fall back to "Instagram" — the most common ground-truth for
 * small-business founders, and a platform every content type works
 * on. We deliberately avoid throwing here because the modal already
 * has its own error surface for the LLM call itself; an Instagram
 * default produces a usable post the founder can copy regardless.
 */
async function resolvePlatform(explicit: string | null): Promise<string> {
  if (explicit && explicit.trim()) return explicit.trim();
  try {
    const profile = await api.business.get();
    if (
      profile &&
      Array.isArray(profile.preferred_platforms) &&
      profile.preferred_platforms.length > 0
    ) {
      return profile.preferred_platforms[0];
    }
  } catch {
    /* profile lookup is best-effort */
  }
  return DEFAULT_PLATFORM;
}

function friendlyError(raw: string): string {
  const lowered = raw.toLowerCase();
  if (lowered.includes("503") || lowered.includes("unavailable")) {
    return "The AI provider was under heavy load. Try again in a moment.";
  }
  if (lowered.includes("429") || lowered.includes("rate")) {
    return "We hit the AI provider's rate limit. Wait 30 seconds and try again.";
  }
  if (lowered.includes("truncated") || lowered.includes("max_tokens")) {
    return "The AI ran past its limit on the first try. Try again — most of these clear immediately.";
  }
  if (lowered.includes("network")) {
    return "Couldn't reach the AI service. Check your connection and retry.";
  }
  return "Most errors here are transient. Try again, or customize in the studio.";
}

function confidenceBand(confidence: number): { label: string; cls: string } {
  if (confidence >= 80)
    return {
      label: "High confidence",
      cls: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
    };
  if (confidence >= 60)
    return {
      label: "Medium confidence",
      cls: "bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/30",
    };
  if (confidence >= 40)
    return {
      label: "Low confidence",
      cls: "bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30",
    };
  return {
    label: "Speculative",
    cls: "bg-muted text-muted-foreground border-border",
  };
}

const CONTENT_TYPE_LABEL: Partial<Record<ContentType, string>> = {
  social_post: "Social post",
  reel: "Reel / Short",
  carousel: "Carousel",
  ad_copy: "Ad copy",
};

function prettyContentType(t: ContentType): string {
  // Phase 6.2 — 37 content types; humanise the slug for those without a label.
  return (
    CONTENT_TYPE_LABEL[t] ??
    t.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase())
  );
}

/**
 * Build the "Customize in studio" deep-link.
 *
 * Mirrors `buildGeneratorHref` from `opportunity-card.tsx` but for the
 * Content studio specifically. When called from the result panel, we
 * prefer the platform actually used (from the result), not the
 * request's nullable one.
 */
export function buildCustomizeHref(
  context: QuickGenerateContext,
  result: GeneratedContent | null,
): string {
  const params = new URLSearchParams();
  params.set("type", context.request.content_type);
  const platform = result?.platform ?? context.request.platform;
  if (platform) params.set("platform", platform);
  if (context.request.goal) params.set("goal", context.request.goal);
  return `/content?${params.toString()}`;
}

// ----------------------------------------------------------------------
//  Context builders — keep the per-callsite conversions in one place
// ----------------------------------------------------------------------

/**
 * The Opportunity Center can return formats the content backend
 * doesn't accept (e.g. "blog_outline"). We coerce the close cousins
 * (`short_video_script` → `reel`) and refuse the rest so callers can
 * hide the Quick Generate button instead of producing a request the
 * server would reject.
 */
const CONTENT_TYPE_SET = new Set<string>([
  "social_post",
  "reel",
  "carousel",
  "ad_copy",
]);

function coerceContentType(format: string): ContentType | null {
  if (format === "short_video_script") return "reel";
  if (CONTENT_TYPE_SET.has(format)) return format as ContentType;
  return null;
}

const IMPACT_SHORT: Record<OpportunityImpactCategory, string> = {
  revenue: "Revenue",
  lead: "Leads",
  customer: "Customers",
  time: "Time",
  cost: "Cost",
};

/**
 * Derive a QuickGenerateContext from a content opportunity.
 *
 * Returns `null` for ad opportunities (they live in the /ads studio)
 * and for content formats the content backend doesn't accept. Callers
 * can use the null return as "don't render the button".
 */
export function quickGenerateFromOpportunity(
  opp: Opportunity,
): QuickGenerateContext | null {
  if (opp.generator.target !== "content") return null;
  const contentType = coerceContentType(opp.generator.format);
  if (!contentType) return null;
  return {
    request: {
      content_type: contentType,
      platform: opp.generator.platform,
      goal: opp.generator.goal,
    },
    source: {
      label: `Opportunity · ${IMPACT_SHORT[opp.impact_category]}`,
      headline: opp.headline,
      reason: opp.reason,
      expectedResult: opp.expected_result,
      confidence: opp.confidence,
    },
    recommendationId: opp.id,
  };
}

/**
 * Derive a QuickGenerateContext from a trending topic.
 *
 * Trends don't carry structured generator hints, so we fall back to:
 *  - content_type: "social_post" (works for every channel, lowest
 *    production friction for a founder).
 *  - platform: null (drawer resolves to the founder's first preferred
 *    platform, then "Instagram").
 *  - goal: the topic's `recommended_action` if present, otherwise a
 *    safe "Ride the ${topic} conversation" phrasing.
 *
 * Trends that lack the Constitution advisory fields entirely (legacy
 * reports) return `null` so we don't surface a Generate button without
 * a "Why we're making this" surface to back it up.
 */
export function quickGenerateFromTrend(
  topic: TrendingTopic,
): QuickGenerateContext | null {
  const hasAdvisory =
    !!topic.recommended_action &&
    !!topic.expected_result &&
    typeof topic.confidence === "number" &&
    !!topic.reason;
  if (!hasAdvisory) return null;
  const goal =
    topic.recommended_action ??
    topic.suggested_angles[0] ??
    `Ride the ${topic.topic} conversation`;
  return {
    request: {
      content_type: "social_post",
      platform: null,
      goal,
    },
    source: {
      label: `Trend · ${topic.topic}`,
      headline: `Ride: ${topic.topic}`,
      reason: topic.reason!,
      expectedResult: topic.expected_result!,
      confidence: topic.confidence!,
    },
  };
}

