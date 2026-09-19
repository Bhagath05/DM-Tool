"use client";

/**
 * AI-vs-Human Creative panel — the evidence-driven verdict on whether the
 * brand's AI-generated creative is actually helping or hurting, versus
 * human-created creative, on real performance data.
 *
 * Reads GET /advisor/creative-evaluation (deterministic, no LLM). It is
 * deliberately honest: it distinguishes VERIFIED evidence from INSUFFICIENT
 * evidence, names which metrics were and were NOT available, never implies a
 * revenue effect that wasn't measured, and always shows that the resulting
 * recommendation needs human approval. When AI is underperforming it recommends
 * human creators / UGC / a controlled test — never "just generate more AI".
 *
 * Bonus panel: it fetches defensively and renders nothing on error, so it can
 * never take the AI Coach page down.
 */

import { FlaskConical, ShieldCheck, Sparkles, UserRound } from "lucide-react";
import { useEffect, useState } from "react";

import { api, type CreativeEvaluation, type CreativeEvaluationVerdict } from "@/lib/api";
import { cn } from "@/lib/utils";

type Tone = "good" | "watch" | "bad" | "neutral";

const VERDICT: Record<
  CreativeEvaluationVerdict,
  { tone: Tone; label: string; icon: typeof Sparkles }
> = {
  AI_OUTPERFORMING: { tone: "good", label: "AI creative is outperforming", icon: Sparkles },
  AI_UNDERPERFORMING: { tone: "bad", label: "AI creative is underperforming", icon: UserRound },
  HUMAN_OUTPERFORMING: { tone: "bad", label: "Human creative is winning", icon: UserRound },
  NO_SIGNIFICANT_DIFFERENCE: { tone: "watch", label: "No clear winner yet", icon: FlaskConical },
  INSUFFICIENT_EVIDENCE: { tone: "neutral", label: "Not enough evidence yet", icon: FlaskConical },
};

const TONE_CLASS: Record<Tone, string> = {
  good: "bg-good/12 text-good border-good/30",
  watch: "bg-watch/12 text-watch border-watch/30",
  bad: "bg-bad/12 text-bad border-bad/30",
  neutral: "bg-muted text-muted-foreground border-border",
};

export function CreativeEvaluationPanel() {
  const [data, setData] = useState<CreativeEvaluation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const d = await api.advisor.creativeEvaluation();
        if (alive) setData(d);
      } catch {
        /* bonus panel — stay hidden on error */
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (loading || !data) return null;

  const v = VERDICT[data.verdict];
  const Icon = v.icon;
  const insufficient = data.verdict === "INSUFFICIENT_EVIDENCE";

  return (
    <section
      data-testid="creative-evaluation-panel"
      className="flex flex-col gap-4 rounded-2xl border border-border/70 bg-card p-6"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-full border",
              TONE_CLASS[v.tone],
            )}
          >
            <Icon className="h-4 w-4" />
          </span>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              AI vs Human creative
            </p>
            <h3 className="text-base font-semibold" data-testid="ce-verdict">
              {v.label}
            </h3>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {data.evidence_source !== "none" && (
            <span
              data-testid="ce-evidence-source"
              className={cn(
                "rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide",
                data.evidence_source === "provider_verified"
                  ? "border-good/30 bg-good/12 text-good"
                  : "border-border bg-muted text-muted-foreground",
              )}
            >
              {data.evidence_source === "provider_verified"
                ? "Provider-verified"
                : "Local / fixture"}
            </span>
          )}
          {!insufficient && (
            <span
              data-testid="ce-confidence"
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs font-medium",
                TONE_CLASS[v.tone],
              )}
            >
              {data.confidence}% confidence
            </span>
          )}
        </div>
      </header>

      <p className="text-sm text-foreground/90" data-testid="ce-diagnosis">
        {data.diagnosis}
      </p>

      {/* Cohort / provenance — how much comparable, attributable evidence exists. */}
      <p className="text-xs text-muted-foreground" data-testid="ce-cohort">
        Compared {data.ai_sample_size} AI-generated vs {data.human_sample_size} human-created posts
        {data.unknown_sample_size > 0
          ? ` · ${data.unknown_sample_size} excluded (unknown provenance)`
          : ""}
        .
      </p>

      {insufficient ? (
        <p
          data-testid="ce-insufficient"
          className="rounded-lg border border-dashed border-border bg-muted/40 p-3 text-sm text-muted-foreground"
        >
          There isn&apos;t enough comparable, provenance-labelled performance data to conclude
          whether AI or human creative performs better. We won&apos;t guess — connect a channel,
          label existing posts, or publish a small human-created test batch to build the evidence.
        </p>
      ) : (
        <>
          {/* Recommendation + why + expected impact */}
          <div className="rounded-lg border border-border bg-background/60 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Recommendation
            </p>
            <p className="mt-1 text-sm font-medium" data-testid="ce-recommendation">
              {data.recommended_action}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground/80">Expected impact: </span>
              {data.expected_impact}
            </p>
          </div>

          {/* VERIFIED evidence — the metrics actually compared */}
          {data.metric_deltas.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                Evidence (measured)
              </p>
              <ul className="flex flex-col gap-1">
                {data.metric_deltas.map((d) => (
                  <li
                    key={d.metric}
                    className="flex items-center justify-between text-sm"
                    data-testid={`ce-metric-${d.metric}`}
                  >
                    <span className="text-foreground/80">{d.label}</span>
                    <span
                      className={cn(
                        "tabular-nums",
                        d.significant
                          ? d.ai_better
                            ? "text-good"
                            : "text-bad"
                          : "text-muted-foreground",
                      )}
                    >
                      AI {d.relative_delta >= 0 ? "+" : ""}
                      {Math.round(d.relative_delta * 100)}% vs human
                      {d.significant ? "" : " (not significant)"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Alternatives / next experiment */}
          {data.alternatives.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                What to try next
              </p>
              <ul className="list-disc pl-5 text-sm text-foreground/80">
                {data.alternatives.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {/* Limitations — always shown so the UI never looks more certain than the data */}
      {data.evidence_limitations.length > 0 && (
        <div className="flex flex-col gap-1" data-testid="ce-limitations">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Evidence limitations
          </p>
          <ul className="list-disc pl-5 text-xs text-muted-foreground">
            {data.evidence_limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Risks + assumptions (compact) */}
      {(data.risks.length > 0 || data.assumptions.length > 0) && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer select-none font-medium text-foreground/70">
            Assumptions &amp; risks
          </summary>
          {data.assumptions.length > 0 && (
            <div className="mt-2">
              <span className="font-medium text-foreground/70">Assumptions: </span>
              {data.assumptions.join(" ")}
            </div>
          )}
          {data.risks.length > 0 && (
            <div className="mt-1">
              <span className="font-medium text-foreground/70">Risks: </span>
              {data.risks.join(" ")}
            </div>
          )}
        </details>
      )}

      {/* Human-in-the-loop — always. */}
      <div
        data-testid="ce-approval"
        className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
      >
        <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
        <span>
          Advisory only — you review and approve before anything is produced, published, or spent.
          Nothing here runs automatically.
        </span>
      </div>
    </section>
  );
}
