"use client";

/**
 * Business Brain panel — evidence-backed research on top of Brand Brain.
 * Shows real job state only (no fake progress timers).
 */

import { Globe, Loader2, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import {
  api,
  type BusinessBrainCompetitorCandidate,
  type BusinessBrainEvidenceItem,
  type BusinessBrainIcp,
  type BusinessBrainMarketSignal,
  type BusinessBrainResearchJob,
  type BusinessBrainSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<string, string> = {
  fact: "Fact",
  observation: "Observation",
  hypothesis: "Hypothesis",
  recommendation: "Recommendation",
};

export function BusinessBrainPanel() {
  const tenant = useTenant();
  const canSetup = tenant.can("settings.manage");

  const [summary, setSummary] = useState<BusinessBrainSummary | null>(null);
  const [evidence, setEvidence] = useState<BusinessBrainEvidenceItem[]>([]);
  const [icps, setIcps] = useState<BusinessBrainIcp[]>([]);
  const [icpMessage, setIcpMessage] = useState<string | null>(null);
  const [competitors, setCompetitors] = useState<BusinessBrainCompetitorCandidate[]>([]);
  const [competitorStatus, setCompetitorStatus] = useState<string | null>(null);
  const [competitorMessage, setCompetitorMessage] = useState<string | null>(null);
  const [marketSignals, setMarketSignals] = useState<BusinessBrainMarketSignal[]>([]);
  const [marketStatus, setMarketStatus] = useState<string | null>(null);
  const [marketMessage, setMarketMessage] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [competitorUrl, setCompetitorUrl] = useState("");
  const [job, setJob] = useState<BusinessBrainResearchJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [s, e, i, c, m] = await Promise.all([
        api.businessBrain.summary(),
        api.businessBrain.evidence(),
        api.businessBrain.listIcps(),
        api.businessBrain.listCompetitors(),
        api.businessBrain.listMarket(),
      ]);
      setSummary(s);
      setEvidence(e.items);
      setIcps(i.items);
      setIcpMessage(i.message);
      setCompetitors(c.candidates);
      setCompetitorStatus(c.status);
      setCompetitorMessage(c.message);
      setMarketSignals(m.signals);
      setMarketStatus(m.status);
      setMarketMessage(m.message);
      if (s.website) setUrl((prev) => prev || s.website || "");
      if (s.latest_job) setJob(s.latest_job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load Business Brain.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll only while a job is actually queued/running.
  useEffect(() => {
    if (!job || (job.status !== "queued" && job.status !== "running")) return;
    const t = window.setInterval(async () => {
      try {
        const next = await api.businessBrain.getResearch(job.id);
        setJob(next);
        if (next.status !== "queued" && next.status !== "running") {
          await refresh();
        }
      } catch {
        /* keep last known state */
      }
    }, 2000);
    return () => window.clearInterval(t);
  }, [job, refresh]);

  async function startResearch() {
    if (!canSetup || !url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const started = await api.businessBrain.startWebsiteResearch(url.trim());
      const next = await api.businessBrain.getResearch(started.id);
      setJob(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Research could not start.");
    } finally {
      setBusy(false);
    }
  }

  async function startCompetitorResearch() {
    if (!canSetup) return;
    const urls = competitorUrl
      .split(/[\n,]+/)
      .map((u) => u.trim())
      .filter(Boolean)
      .slice(0, 5);
    setBusy(true);
    setError(null);
    try {
      const started = await api.businessBrain.startCompetitorResearch(urls);
      const next = await api.businessBrain.getResearch(started.id);
      setJob(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Competitor research could not start.");
    } finally {
      setBusy(false);
    }
  }

  async function startMarketResearch() {
    if (!canSetup) return;
    setBusy(true);
    setError(null);
    try {
      const started = await api.businessBrain.startMarketResearch();
      const next = await api.businessBrain.getResearch(started.id);
      setJob(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Market research could not start.");
    } finally {
      setBusy(false);
    }
  }

  async function generateIcps() {
    if (!canSetup) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.businessBrain.generateIcps();
      setIcps(res.items);
      setIcpMessage(res.message);
      if (res.status === "INSUFFICIENT_EVIDENCE") {
        setError(res.message || "Not enough evidence for ICP hypotheses.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "ICP generation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-6 rounded-xl border border-border bg-card/40 p-5">
      <SectionHeading
        heading="Business Brain"
        description="Evidence-backed understanding of your business — facts stay facts, hypotheses stay hypotheses."
      />

      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="bb-url">
          Website to analyze
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Globe className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="bb-url"
              className="pl-9"
              placeholder="https://yourcompany.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={!canSetup || busy}
            />
          </div>
          <Button
            type="button"
            onClick={() => void startResearch()}
            disabled={!canSetup || busy || !url.trim()}
          >
            {busy ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Search className="mr-2 h-4 w-4" />
            )}
            Analyze business
          </Button>
        </div>
        {!canSetup ? (
          <p className="text-sm text-muted-foreground">
            You need settings access to start research.
          </p>
        ) : null}
      </div>

      {job ? (
        <div className="rounded-lg border border-border bg-background/60 px-4 py-3 text-sm">
          <p className="font-medium">
            Research status: {job.status}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              ({job.kind})
            </span>
          </p>
          <p className="text-muted-foreground">
            {job.normalized_url}
            {job.evidence_count > 0 ? ` · ${job.evidence_count} evidence items` : ""}
          </p>
          {job.error_category ? (
            <p className="mt-1 text-amber-700 dark:text-amber-400">
              {job.error_category}
              {job.error_message ? `: ${job.error_message}` : ""}
            </p>
          ) : null}
        </div>
      ) : null}

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {summary ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-semibold">What we know</h3>
            {summary.known.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing confirmed yet.</p>
            ) : (
              <ul className="list-inside list-disc text-sm text-muted-foreground">
                {summary.known.map((k) => (
                  <li key={k}>{k}</li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold">What we don&apos;t know</h3>
            {summary.unknown.length === 0 ? (
              <p className="text-sm text-muted-foreground">No major gaps flagged.</p>
            ) : (
              <ul className="list-inside list-disc text-sm text-muted-foreground">
                {summary.unknown.map((k) => (
                  <li key={k}>{k}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}

      {summary?.limitations?.length ? (
        <div className="rounded-lg border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
          <p className="mb-1 font-medium text-foreground">Limitations</p>
          <ul className="list-inside list-disc">
            {summary.limitations.slice(0, 4).map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Evidence</h3>
        {evidence.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No evidence yet. Analyze a website to collect facts and observations.
          </p>
        ) : (
          <ul className="space-y-2">
            {evidence.slice(0, 20).map((item) => (
              <li
                key={item.id}
                className="rounded-lg border border-border px-3 py-2 text-sm"
              >
                <span
                  className={cn(
                    "mr-2 inline-block rounded px-1.5 py-0.5 text-xs font-medium",
                    item.kind === "fact" && "bg-emerald-500/15 text-emerald-700",
                    item.kind === "observation" && "bg-sky-500/15 text-sky-700",
                    item.kind === "hypothesis" && "bg-amber-500/15 text-amber-800",
                    item.kind === "recommendation" && "bg-violet-500/15 text-violet-700",
                  )}
                >
                  {KIND_LABEL[item.kind] ?? item.kind}
                </span>
                <span className="text-muted-foreground">
                  {item.confidence}% · {item.category}
                </span>
                <p className="mt-1 text-foreground">{item.claim}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex-1 space-y-2">
            <h3 className="text-sm font-semibold">Competitors</h3>
            <p className="text-xs text-muted-foreground">
              Paste competitor website URLs — we research those pages only. We never invent
              competitor companies.
            </p>
            <Input
              placeholder="https://competitor.com (comma or newline separated)"
              value={competitorUrl}
              onChange={(e) => setCompetitorUrl(e.target.value)}
              disabled={!canSetup || busy}
            />
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!canSetup || busy}
            onClick={() => void startCompetitorResearch()}
          >
            Research competitors
          </Button>
        </div>
        {competitorStatus ? (
          <p className="text-sm text-muted-foreground">
            Status: {competitorStatus}
            {competitorMessage ? ` — ${competitorMessage}` : ""}
          </p>
        ) : null}
        {competitors.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No competitor candidates yet. Candidates are labeled as hypotheses until
            supported.
          </p>
        ) : (
          <ul className="space-y-2">
            {competitors.map((c) => (
              <li key={`${c.name}-${c.source_url}`} className="rounded-lg border border-border px-3 py-2 text-sm">
                <p className="font-medium">
                  {c.name}{" "}
                  <span className="text-xs font-normal text-amber-800 dark:text-amber-400">
                    ({c.status} · {c.confidence}% · not a verified fact)
                  </span>
                </p>
                <p className="mt-1 text-muted-foreground">{c.reason}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Market</h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!canSetup || busy}
            onClick={() => void startMarketResearch()}
          >
            Research market signals
          </Button>
        </div>
        {marketStatus ? (
          <p className="text-sm text-muted-foreground">
            Status: {marketStatus}
            {marketMessage ? ` — ${marketMessage}` : ""}
          </p>
        ) : null}
        {marketSignals.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No market signals yet. Derived from evidence only — never fabricated market size
            or growth figures.
          </p>
        ) : (
          <ul className="space-y-2">
            {marketSignals.map((s, idx) => (
              <li key={`${s.signal_kind}-${idx}`} className="rounded-lg border border-border px-3 py-2 text-sm">
                <span
                  className={cn(
                    "mr-2 inline-block rounded px-1.5 py-0.5 text-xs font-medium",
                    s.evidence_kind === "fact" && "bg-emerald-500/15 text-emerald-700",
                    s.evidence_kind === "observation" && "bg-sky-500/15 text-sky-700",
                    s.evidence_kind === "hypothesis" && "bg-amber-500/15 text-amber-800",
                  )}
                >
                  {KIND_LABEL[s.evidence_kind] ?? s.evidence_kind}
                </span>
                <span className="text-muted-foreground">
                  {s.signal_kind} · {s.confidence}%
                </span>
                <p className="mt-1 text-foreground">{s.claim}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">ICP hypotheses</h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!canSetup || busy}
            onClick={() => void generateIcps()}
          >
            Generate from evidence
          </Button>
        </div>
        {icpMessage ? (
          <p className="text-sm text-muted-foreground">{icpMessage}</p>
        ) : null}
        {icps.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No ICP hypotheses yet. These describe who is likely to buy — not
            campaigns or lead lists.
          </p>
        ) : (
          <ul className="space-y-2">
            {icps.map((icp) => (
              <li key={icp.id} className="rounded-lg border border-border px-3 py-2 text-sm">
                <p className="font-medium">
                  {icp.name}{" "}
                  <span className="text-xs font-normal text-muted-foreground">
                    ({icp.status} · {icp.confidence}% confidence)
                  </span>
                </p>
                <p className="mt-1 text-muted-foreground">{icp.description}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
