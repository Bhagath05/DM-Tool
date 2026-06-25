"use client";

/**
 * Phase 9.1 — Performance Engine card.
 *
 * Single dashboard widget. Three states:
 *
 *   1. EMPTY  — brand has never uploaded a CSV. Render the dashed
 *               "Upload performance CSV" CTA so the founder can get
 *               their first insight.
 *
 *   2. THINKING — backend has rows but no diagnostic survived the
 *                 min-sample gate. Render a `<ComingSoonCard>` style
 *                 explanation rather than fabricating numbers.
 *
 *   3. READY — render the top diagnostic(s) through `<AiRecommendation>`,
 *              with a small "upload fresh data" affordance so the
 *              founder can keep iterating without leaving the page.
 *
 * Every output goes through Constitution-shaped primitives — no
 * bespoke layout. The translator (lib/performance-translator) has
 * already enforced contract integrity by the time we render.
 */

import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  RotateCcw,
  Sparkles,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { AiRecommendation } from "@/components/ui/business-metric";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  api,
  ApiError,
  type CsvIngestSummary,
  type PerformanceOverview,
} from "@/lib/api";
import { derive } from "@/lib/performance-derived";
import {
  groupBySection,
  translateOverview,
  type PerformanceCards,
  type PerformanceOpportunity,
} from "@/lib/performance-translator";
import { useViewMode } from "@/lib/use-view-mode";
import { cn } from "@/lib/utils";

/**
 * Simple Mode shows at most this many cards (Constitution: founder
 * sees ≤3 actions at a time). Pro Mode shows all 7.
 */
const SIMPLE_MODE_CARD_CAP = 3;

// ---------------------------------------------------------------------
//  State machine
// ---------------------------------------------------------------------

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: PerformanceCards };

// ---------------------------------------------------------------------
//  Main component
// ---------------------------------------------------------------------

export function PerformanceEngineCard() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [uploadStatus, setUploadStatus] = useState<
    | { kind: "idle" }
    | { kind: "uploading" }
    | { kind: "success"; summary: CsvIngestSummary }
    | { kind: "error"; message: string }
  >({ kind: "idle" });
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const overview = await api.performance.overview();
      setState({ kind: "ready", data: translateOverview(overview) });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not load performance data";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onFile = useCallback(
    async (file: File) => {
      setUploadStatus({ kind: "uploading" });
      try {
        const summary = await api.performance.upload(file);
        setUploadStatus({ kind: "success", summary });
        await load();
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "Upload failed";
        setUploadStatus({ kind: "error", message });
      }
    },
    [load],
  );

  const onReset = useCallback(async () => {
    // Native confirm is fine — this is a destructive irreversible
    // action, and the founder needs a real "are you sure" moment. A
    // custom modal is over-engineering for the dev path; we can
    // upgrade to a Dialog primitive when we add other dangerous
    // affordances.
    const ok = window.confirm(
      "Clear all uploaded performance data for this brand?\n\n" +
        "This deletes every ingested CSV row, rollup, and diagnostic. " +
        "You'll start with a clean slate. Your generated creatives are not affected.",
    );
    if (!ok) return;
    try {
      await api.performance.resetData();
      setUploadStatus({ kind: "idle" });
      await load();
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not reset data";
      setUploadStatus({ kind: "error", message });
    }
  }, [load]);

  // Show the Reset affordance only when there's data worth resetting.
  const hasIngestedData =
    state.kind === "ready" && state.data.rowsIngested > 0;

  return (
    <Card data-testid="performance-engine-card">
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-violet-500" />
            Performance Coach
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Upload your ad export and we'll tell you what's working — and
            where to put your next spend.
          </p>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          data-testid="performance-csv-input"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void onFile(f);
            // Reset so the same file can be re-selected.
            e.target.value = "";
          }}
        />
        <div className="flex items-center gap-2">
          {hasIngestedData && (
            <Button
              variant="outline"
              size="sm"
              onClick={onReset}
              data-testid="performance-reset-button"
              className="text-muted-foreground hover:text-bad-soft-foreground hover:border-bad-border"
              title="Wipe all ingested CSV data for this brand. Cannot be undone."
            >
              <RotateCcw className="mr-2 h-3.5 w-3.5" />
              Reset data
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={uploadStatus.kind === "uploading"}
            onClick={() => fileRef.current?.click()}
            data-testid="performance-upload-button"
          >
            {uploadStatus.kind === "uploading" ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Uploading…
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                Upload CSV
              </>
            )}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Upload feedback banner — separate from the main body so it
            shows alongside whatever state the card is in. */}
        {uploadStatus.kind === "success" && (
          <UploadSummaryBanner summary={uploadStatus.summary} />
        )}
        {uploadStatus.kind === "error" && (
          <ErrorBanner message={uploadStatus.message} />
        )}

        {state.kind === "loading" && <LoadingBlock />}
        {state.kind === "error" && <ErrorBanner message={state.message} />}
        {state.kind === "ready" && <ReadyBody data={state.data} />}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------
//  Sub-views
// ---------------------------------------------------------------------

function ReadyBody({ data }: { data: PerformanceCards }) {
  const { mode } = useViewMode();

  if (data.rowsIngested === 0) {
    return <EmptyState />;
  }
  if (!data.hasUsableCards) {
    return (
      <NotEnoughDataState
        rowsIngested={data.rowsIngested}
        creativesTracked={data.creativesTracked}
      />
    );
  }

  // Simple Mode = top-3 cards by confidence, no sectioning.
  // Pro Mode   = all cards, grouped by intelligence section.
  if (mode !== "professional") {
    const top = data.cards.slice(0, SIMPLE_MODE_CARD_CAP);
    return (
      <div className="space-y-4" data-testid="performance-cards">
        {top.map((c) => (
          <PerformanceCardRow key={c.id} card={c} />
        ))}
        {data.cards.length > top.length && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="performance-more-hint"
          >
            {data.cards.length - top.length} more insight
            {data.cards.length - top.length === 1 ? "" : "s"} available — switch
            to Pro view to see them.
          </p>
        )}
      </div>
    );
  }

  // Pro Mode — group by intelligence section.
  const sections = groupBySection(data.cards);
  return (
    <div className="space-y-6" data-testid="performance-cards">
      {sections.map(({ section, label, cards }) => (
        <section
          key={section}
          data-testid={`performance-section-${section}`}
          className="space-y-3"
        >
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {label}
          </h4>
          {cards.map((c) => (
            <PerformanceCardRow key={c.id} card={c} />
          ))}
        </section>
      ))}
    </div>
  );
}

function PerformanceCardRow({ card }: { card: PerformanceOpportunity }) {
  const d = derive(card);
  return (
    <AiRecommendation
      data-testid={`performance-card-${card.kind}`}
      whatIsHappening={card.whatIsHappening}
      impactCategory={card.impactCategory}
      recommendation={card.recommendation}
      expectedResult={card.expectedResult}
      confidence={card.confidence}
      reason={card.reason}
      technicalDetails={card.technicalDetails}
      chips={{
        priority: d.priority,
        effort: d.effort,
        expectedLeads: d.expectedLeads ?? undefined,
        revenueImpact: d.revenueImpact ?? undefined,
      }}
    />
  );
}

function EmptyState() {
  return (
    <div
      data-testid="performance-empty"
      className="flex flex-col items-start gap-2 rounded-2xl border border-dashed border-border bg-muted/20 p-6 text-sm"
    >
      <p className="text-card-title text-foreground">No performance data yet.</p>
      <p className="text-muted-foreground">
        Drop your last 30 days from Meta Ads Manager (or any platform)
        into the uploader above. We'll tell you which creative is
        winning and where to put your next spend.
      </p>
      <p className="text-xs text-muted-foreground/80">
        Tip: CSV exports up to 2 MB · live connectors arrive in the next phase.
      </p>
    </div>
  );
}

function NotEnoughDataState({
  rowsIngested,
  creativesTracked,
}: {
  rowsIngested: number;
  creativesTracked: number;
}) {
  return (
    <div
      data-testid="performance-coming-soon"
      className="flex flex-col items-start gap-2 rounded-2xl border border-dashed border-border bg-muted/20 p-6 text-sm"
    >
      <p className="text-card-title text-foreground">
        Not enough data to call a winner yet.
      </p>
      <p className="text-muted-foreground">
        We have {rowsIngested.toLocaleString()} rows across{" "}
        {creativesTracked} {creativesTracked === 1 ? "creative" : "creatives"},
        but none have hit the minimum sample size yet.
      </p>
      <p className="text-xs text-muted-foreground/80">
        Threshold: 500 impressions · ~1,000 spend · 1+ lead per creative. Keep
        running them — we'll surface a recommendation as soon as the numbers
        are reliable.
      </p>
    </div>
  );
}

function LoadingBlock() {
  return (
    <div
      data-testid="performance-loading"
      className="card-surface flex items-center gap-3 p-5 text-sm text-muted-foreground"
    >
      <Loader2 className="h-4 w-4 animate-spin text-ai" />
      Loading your performance insights…
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      data-testid="performance-error"
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

function UploadSummaryBanner({ summary }: { summary: CsvIngestSummary }) {
  const range = summary.date_range
    ? `${summary.date_range[0]} → ${summary.date_range[1]}`
    : null;
  const matched = summary.creatives_matched;
  return (
    <div
      data-testid="performance-upload-summary"
      className={cn(
        "flex items-start gap-2 rounded-md border p-3 text-sm",
        summary.rows_rejected > 0
          ? "border-amber-500/30 bg-amber-500/10 text-amber-900 dark:text-amber-100"
          : "border-emerald-500/30 bg-emerald-500/10 text-emerald-900 dark:text-emerald-100",
      )}
    >
      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="space-y-1">
        <p className="font-medium">
          Uploaded {summary.rows_accepted.toLocaleString()} rows
          {range ? ` (${range})` : ""}.
        </p>
        <p className="text-muted-foreground">
          {matched > 0
            ? `Matched ${matched} ${matched === 1 ? "creative" : "creatives"} to ones we've generated for you.`
            : `Didn't match any rows to your generated creatives — that's fine, we still tag them as external for the rollup.`}
          {summary.rows_rejected > 0
            ? ` ${summary.rows_rejected} row${summary.rows_rejected === 1 ? " was" : "s were"} skipped — see the errors below.`
            : ""}
        </p>
        {summary.errors.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-xs">
            {summary.errors.slice(0, 5).map((e) => (
              <li key={e.row_number}>
                Row {e.row_number}: {e.error}
              </li>
            ))}
            {summary.errors.length > 5 && (
              <li>… and {summary.errors.length - 5} more.</li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
