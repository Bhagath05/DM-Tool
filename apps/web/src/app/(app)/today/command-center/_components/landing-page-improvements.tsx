"use client";

/**
 * Phase 10.4 — Landing Page Improvements.
 *
 *   📄 LANDING PAGE IMPROVEMENTS
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ "Free Audit" page · High priority                            │
 *   │ Issue: No call-to-action                                     │
 *   │ Fix:   Add 'Get a free audit' as the button label            │
 *   │ [ Open page → ]                                              │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * Fetches `api.landingPages.list()` and runs the heuristic audit
 * client-side (see `lib/landing-page-audit.ts`). Shows the top 5
 * findings ranked severity DESC.
 *
 * Honest framing: the section heading and per-card label both name
 * these as heuristic ("smart checks"), not LLM-grade analysis. The
 * audit confidence is capped at 70 to reinforce that.
 */

import { ArrowRight, FileText, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { api, ApiError } from "@/lib/api";
import {
  auditLandingPages,
  type AuditFinding,
} from "@/lib/landing-page-audit";
import { cn } from "@/lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty"; message: string }
  | { kind: "ready"; findings: AuditFinding[] };

const MAX_FINDINGS = 5;

const SEVERITY_TONE: Record<
  AuditFinding["severity"],
  "good" | "watch" | "bad"
> = {
  high: "bad",
  medium: "watch",
  low: "good",
};

const SEVERITY_LABEL: Record<AuditFinding["severity"], string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

export function LandingPageImprovements({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const pages = await api.landingPages.list();
      if (!pages || pages.length === 0) {
        setState({
          kind: "empty",
          message:
            "Create your first landing page to start receiving conversion improvement recommendations.",
        });
        return;
      }
      const findings = auditLandingPages(pages).slice(0, MAX_FINDINGS);
      if (findings.length === 0) {
        setState({
          kind: "empty",
          message:
            "Your published landing pages pass every quick-check. Keep an eye on conversion in Results.",
        });
        return;
      }
      setState({ kind: "ready", findings });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Couldn't audit your landing pages.";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="landing-page-improvements"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <FileText className="h-3 w-3" />
            Landing page improvements
          </span>
        }
        heading="Quick fixes to lift your conversion"
        description="Smart-check findings from your published pages. Heuristic, not LLM — high-leverage, low-effort wins."
      />

      {state.kind === "loading" && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <EmptyState
          icon={Sparkles}
          title="Audit unavailable"
          description={state.message}
          data-testid="landing-page-improvements-error"
        />
      )}

      {state.kind === "empty" && (
        <EmptyState
          icon={FileText}
          title="No improvements to suggest"
          description={state.message}
          data-testid="landing-page-improvements-empty"
        />
      )}

      {state.kind === "ready" && (
        <ul
          className="flex flex-col gap-2"
          data-testid="landing-page-improvements-list"
        >
          {state.findings.map((f) => (
            <FindingRow key={f.id} finding={f} />
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Row
// ---------------------------------------------------------------------

function FindingRow({ finding }: { finding: AuditFinding }) {
  const href = `/landing-pages/${finding.page_id}?from=command-center`;
  return (
    <li>
      <article
        data-testid={`landing-finding-${finding.id}`}
        className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4 sm:flex-row sm:items-start"
      >
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <header className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-foreground">
              {finding.title}
            </span>
            <StatusPill
              tone={SEVERITY_TONE[finding.severity]}
              size="sm"
              dot
              className="ml-auto"
            >
              {SEVERITY_LABEL[finding.severity]} · {finding.confidence}%
            </StatusPill>
          </header>
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Page: </span>
            {finding.page_title}
          </p>
          <p className="text-sm font-medium text-foreground">
            <span className="text-muted-foreground">Fix: </span>
            {finding.recommendation}
          </p>
        </div>

        <Link
          href={href as never}
          className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
        >
          Open page
          <ArrowRight className="h-3 w-3" />
        </Link>
      </article>
    </li>
  );
}
