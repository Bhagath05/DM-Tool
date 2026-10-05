"use client";

/**
 * Renders a real Marketing Brain AgentResponse as a structured experience.
 *
 * It renders ONLY what the agent returned — no fabricated metrics or results.
 * The answer prose leads; structured blocks (observations, evidence, proposed
 * approvals) follow; the reasoning summary is progressive-disclosure. A proposed
 * consequential action is shown as "approval required" and links to the approval
 * surface — it is NEVER presented as done.
 */

import { ChevronRight } from "lucide-react";

import {
  ApprovalRequestBlock,
  ClaimBlock,
  EvidenceBlock,
  GenBlock,
  InsightBlock,
  InsufficientEvidenceBlock,
  TrustConfidence,
  TrustMetricCard,
  TrustRecommendation,
  TrustStatusPill,
  TrustSummaryBlock,
} from "@/components/brain/blocks";
import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { StatusPill } from "@/components/ui/status-pill";
import type { AgentResponse, TrustEnvelope } from "@/lib/api";

function Prose({ text }: { text: string }) {
  // Split into paragraphs on blank lines; keep each readable (no giant wall).
  const paras = text.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  return (
    <div className="flex flex-col gap-2 text-sm leading-relaxed">
      {paras.length > 0 ? paras.map((p, i) => <p key={i}>{p}</p>) : <p>{text}</p>}
    </div>
  );
}

function AnswerFooter({
  evidenceStatus,
  confidence,
}: {
  evidenceStatus: AgentResponse["evidence_status"];
  confidence: number;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      <StatusPill tone={evidenceStatus === "ok" ? "good" : "watch"}>
        {evidenceStatus === "ok" ? "Evidence-backed" : "Insufficient evidence"}
      </StatusPill>
      {confidence > 0 && (
        <span className="inline-flex items-center gap-2">
          <span>Confidence</span>
          <span className="w-24">
            <ConfidenceBar value={confidence} size="sm" hideLabel />
          </span>
          <span className="tabular font-medium text-foreground">{confidence}%</span>
        </span>
      )}
    </div>
  );
}

/** The server-authoritative trust header for the lead answer. */
function TrustHeader({ trust }: { trust: TrustEnvelope }) {
  return (
    <div className="mt-3 flex flex-col gap-2 border-t border-border pt-3">
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <TrustStatusPill status={trust.status} />
        <span className="min-w-0">{trust.safe_language}</span>
      </div>
      {trust.server_confidence > 0 && <TrustConfidence value={trust.server_confidence} />}
    </div>
  );
}

export function AgentAnswer({ response }: { response: AgentResponse }) {
  const trust = response.trust ?? null;
  const insufficient = response.evidence_status === "INSUFFICIENT_EVIDENCE";
  return (
    <div className="flex flex-col gap-3" data-testid="brain-answer">
      {/* Lead answer. The trust header (status + confidence) is server-derived. */}
      {response.answer && (
        <div className="rounded-xl border border-border bg-card p-4">
          <Prose text={response.answer} />
          {trust ? (
            <TrustHeader trust={trust} />
          ) : (
            <div className="mt-3 border-t border-border pt-3">
              <AnswerFooter evidenceStatus={response.evidence_status} confidence={response.confidence} />
            </div>
          )}
        </div>
      )}

      {/* T4: structured, server-validated claims — fact vs interpretation vs
          hypothesis made visually distinct. */}
      {trust && trust.claims.length > 0 && (
        <div className="flex flex-col gap-2" data-testid="brain-claims">
          {trust.claims.map((c, i) => (
            <ClaimBlock key={`${c.statement.slice(0, 24)}-${i}`} claim={c} />
          ))}
        </div>
      )}

      {/* T4: metrics from the deterministic registry — invalid ones show
          "Not available", never a fabricated number. */}
      {trust && trust.metrics.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" data-testid="brain-metrics">
          {trust.metrics.map((m, i) => (
            <TrustMetricCard key={`${m.name}-${i}`} metric={m} />
          ))}
        </div>
      )}

      {/* T4: recommendations, visibly distinct from facts, with consequence. */}
      {trust &&
        trust.recommendations.map((r, i) => (
          <TrustRecommendation key={`${r.action}-${i}`} rec={r} />
        ))}

      {insufficient && (
        <InsufficientEvidenceBlock detail={response.reasoning_summary?.uncertainty || undefined} />
      )}

      {response.reasoning_summary?.key_observations?.length > 0 && (
        <InsightBlock observations={response.reasoning_summary.key_observations} />
      )}

      {/* PROPOSED consequential actions → approval required, never executed. */}
      {response.proposed_actions.map((a) => (
        <ApprovalRequestBlock
          key={a.approval_id}
          tool={a.tool_name}
          explanation={a.explanation}
          reason={a.reason}
          expectedEffect={a.expected_effect}
          status={a.status}
        />
      ))}

      {/* T4: compact, server-derived trust roll-up. */}
      {trust && <TrustSummaryBlock summary={trust.summary} />}

      <EvidenceBlock
        sources={response.evidence.map((e) => ({
          label: e.label,
          source: e.source,
          confidence: e.confidence,
          status: e.status,
        }))}
        toolsConsulted={response.tools_consulted}
      />

      {/* Reasoning summary — progressive disclosure, not chain-of-thought. */}
      {response.reasoning_summary && (
        <details className="group rounded-xl border border-border bg-card" data-testid="brain-reasoning">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-xs font-medium text-muted-foreground hover:text-foreground">
            <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" aria-hidden />
            How the Brain reasoned
          </summary>
          <div className="border-t border-border px-4 py-3 text-xs text-muted-foreground">
            {response.reasoning_summary.intent && (
              <p>
                <span className="font-medium text-foreground">Intent:</span>{" "}
                {response.reasoning_summary.intent}
              </p>
            )}
            {response.reasoning_summary.evidence_used.length > 0 && (
              <p className="mt-1">
                <span className="font-medium text-foreground">Evidence used:</span>{" "}
                {response.reasoning_summary.evidence_used.join(", ")}
              </p>
            )}
            {response.reasoning_summary.uncertainty && (
              <p className="mt-1">
                <span className="font-medium text-foreground">Uncertainty:</span>{" "}
                {response.reasoning_summary.uncertainty}
              </p>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

/**
 * Render a historical assistant message from its persisted content + safe meta
 * (the API returns full structure only for the live turn). Still never implies
 * execution — a recorded approval request links out to the approval surface.
 */
export function HistoricalAssistantAnswer({
  content,
  meta,
}: {
  content: string;
  meta: Record<string, unknown>;
}) {
  const evidenceStatus = meta.evidence_status === "INSUFFICIENT_EVIDENCE" ? "INSUFFICIENT_EVIDENCE" : "ok";
  const confidence = typeof meta.confidence === "number" ? meta.confidence : 0;
  const tools = Array.isArray(meta.tools_consulted) ? (meta.tools_consulted as string[]) : [];
  const approvals = Array.isArray(meta.approvals_requested)
    ? (meta.approvals_requested as string[])
    : [];
  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-xl border border-border bg-card p-4">
        <Prose text={content} />
        <div className="mt-3 border-t border-border pt-3">
          <AnswerFooter
            evidenceStatus={evidenceStatus as AgentResponse["evidence_status"]}
            confidence={confidence}
          />
        </div>
      </div>
      {tools.length > 0 && <EvidenceBlock sources={[]} toolsConsulted={tools} />}
      {approvals.length > 0 && (
        <GenBlock eyebrow="Approval required" accent>
          <p className="text-sm">
            This turn proposed {approvals.length === 1 ? "an action" : `${approvals.length} actions`}{" "}
            that still need your approval. Nothing has run.
          </p>
          <a
            href="/ai/approvals"
            className="mt-2 inline-block text-xs font-medium text-ai underline-offset-4 hover:underline"
          >
            Review &amp; decide →
          </a>
        </GenBlock>
      )}
    </div>
  );
}
