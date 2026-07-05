"use client";

/**
 * Phase 6.5 Slice 5 — reusable AI Sales Assistant insight panel.
 *
 * Generates + renders a grounded insight for any CRM subject. Shows the full
 * evidence contract (recommendation · confidence · reasoning · evidence viewer ·
 * affected records · expected outcome · generated/expires) and the honest
 * "Not enough evidence." state. Used from the contact/company detail modal and
 * the deal board. Design system reused.
 */

import { AlertCircle, Info, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { Surface } from "@/components/ui/surface";
import { api, type CrmInsight, type CrmInsightSubject } from "@/lib/api";
import { humanize } from "@/lib/crm-format";

// Constitution confidence bands.
function confidenceBand(c: number): { tone: PillTone; label: string } {
  if (c >= 80) return { tone: "good", label: "High confidence" };
  if (c >= 60) return { tone: "watch", label: "Medium confidence" };
  if (c >= 40) return { tone: "watch", label: "Low confidence" };
  return { tone: "muted", label: "Speculative" };
}

export function AIInsightPanel({
  subjectType,
  subjectId,
  kind,
}: {
  subjectType: CrmInsightSubject;
  subjectId: string;
  kind?: string;
}) {
  const [insight, setInsight] = useState<CrmInsight | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load the most recent cached insight for this subject (no LLM spend).
  const loadCached = useCallback(async () => {
    setLoading(true);
    try {
      const items = await api.crm.insights({ subject_type: subjectType, subject_id: subjectId });
      setInsight(items[0] ?? null);
    } finally {
      setLoading(false);
    }
  }, [subjectType, subjectId]);

  useEffect(() => {
    void loadCached();
  }, [loadCached]);

  const generate = async (force = false) => {
    setBusy(true);
    setError(null);
    try {
      setInsight(await api.crm.generateInsight(subjectType, subjectId, { kind, force }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate insight.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2" data-testid="ai-insight-panel">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5" /> AI Sales Assistant
        </p>
        <Button size="sm" variant="outline" onClick={() => void generate(!!insight)} disabled={busy}
          data-testid="ai-insight-generate">
          {busy ? "Analyzing…" : insight ? "Regenerate" : "Generate insight"}
        </Button>
      </div>

      {error && <Surface state="bad" padding="compact" className="text-xs text-bad">{error}</Surface>}

      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : !insight ? (
        <p className="text-xs text-muted-foreground">
          No insight yet — generate a grounded recommendation from this record&apos;s CRM data.
        </p>
      ) : insight.insufficient_evidence ? (
        <Surface state="watch" padding="compact" className="space-y-1" data-testid="ai-insight-insufficient">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            <AlertCircle className="h-4 w-4" /> Not enough evidence.
          </p>
          <p className="text-xs text-muted-foreground">{insight.reasoning}</p>
        </Surface>
      ) : (
        <Surface state="ai" padding="compact" className="space-y-2" data-testid="ai-insight-card">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill tone={confidenceBand(insight.confidence).tone} size="sm">
              {insight.confidence}% · {confidenceBand(insight.confidence).label}
            </StatusPill>
            <StatusPill tone="neutral" size="sm">{humanize(insight.kind)}</StatusPill>
          </div>

          {insight.recommendation && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">Recommendation</p>
              <p className="text-sm font-medium">{insight.recommendation}</p>
            </div>
          )}
          {insight.summary && <p className="text-sm">{insight.summary}</p>}
          {insight.expected_outcome && (
            <p className="text-xs"><span className="font-medium">Expected: </span>{insight.expected_outcome}</p>
          )}

          {insight.evidence.length > 0 && (
            <details className="text-xs">
              <summary className="flex cursor-pointer items-center gap-1 font-medium text-muted-foreground">
                <Info className="h-3 w-3" /> Evidence ({insight.evidence.length})
              </summary>
              <ul className="mt-1 space-y-1">
                {insight.evidence.map((e, i) => (
                  <li key={i}>
                    <span className="font-medium">{e.source}:</span> {e.detail}
                  </li>
                ))}
              </ul>
              {insight.reasoning && (
                <p className="mt-1 text-muted-foreground"><span className="font-medium">Reasoning: </span>{insight.reasoning}</p>
              )}
            </details>
          )}

          {insight.affected_records.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {insight.affected_records.map((r) => (
                <StatusPill key={r} tone="muted" size="sm">{r}</StatusPill>
              ))}
            </div>
          )}

          <p className="text-[11px] text-muted-foreground">
            Generated {new Date(insight.generated_at).toLocaleString()}
            {insight.expires_at && ` · expires ${new Date(insight.expires_at).toLocaleDateString()}`}
          </p>
        </Surface>
      )}
    </div>
  );
}
