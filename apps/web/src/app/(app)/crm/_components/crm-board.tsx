"use client";

/**
 * Phase 6.5 — CRM pipeline board (Slice 1 frontend).
 *
 * Kanban over the live /crm API: analytics KPI header, pipeline selector, a
 * column per stage with deal cards, move-between-stages, quick-add deal, and the
 * grounded AI next-action. Design system reused throughout.
 */

import { Plus, Sparkles, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { Surface } from "@/components/ui/surface";
import {
  api,
  type CrmAnalytics,
  type CrmDeal,
  type CrmPipeline,
  type CrmPriority,
} from "@/lib/api";

const PRIORITY_TONE: Record<CrmPriority, PillTone> = {
  low: "muted",
  medium: "neutral",
  high: "watch",
};

function money(v: number, ccy = "USD"): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency", currency: ccy, maximumFractionDigits: 0,
    }).format(v);
  } catch {
    return `${ccy} ${Math.round(v).toLocaleString()}`;
  }
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <Surface padding="compact" className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xl font-semibold">{value}</span>
    </Surface>
  );
}

export function CrmBoard() {
  const [pipelines, setPipelines] = useState<CrmPipeline[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [deals, setDeals] = useState<CrmDeal[]>([]);
  const [analytics, setAnalytics] = useState<CrmAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newValue, setNewValue] = useState("");

  const active = useMemo(
    () => pipelines.find((p) => p.id === activeId) ?? null,
    [pipelines, activeId],
  );

  const loadPipelines = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const ps = await api.crm.pipelines();
      setPipelines(ps);
      setActiveId((cur) => cur ?? ps[0]?.id ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load pipelines.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadBoard = useCallback(async (pipelineId: string) => {
    const [d, a] = await Promise.all([
      api.crm.deals({ pipeline_id: pipelineId }),
      api.crm.analytics(pipelineId),
    ]);
    setDeals(d.items);
    setAnalytics(a);
  }, []);

  useEffect(() => {
    void loadPipelines();
  }, [loadPipelines]);

  useEffect(() => {
    if (activeId) void loadBoard(activeId).catch(() => {});
  }, [activeId, loadBoard]);

  const refresh = () => {
    if (activeId) void loadBoard(activeId).catch(() => {});
  };

  const move = async (deal: CrmDeal, stageId: string) => {
    if (stageId === deal.stage_id) return;
    setBusyId(deal.id);
    try {
      const updated = await api.crm.moveDeal(deal.id, stageId);
      setDeals((prev) => prev.map((x) => (x.id === deal.id ? updated : x)));
      if (activeId) void api.crm.analytics(activeId).then(setAnalytics).catch(() => {});
    } finally {
      setBusyId(null);
    }
  };

  const runNextAction = async (deal: CrmDeal) => {
    setBusyId(deal.id);
    try {
      const updated = await api.crm.nextAction(deal.id);
      setDeals((prev) => prev.map((x) => (x.id === deal.id ? updated : x)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI next-action failed.");
    } finally {
      setBusyId(null);
    }
  };

  const addDeal = async () => {
    if (!active || !newTitle.trim()) return;
    const firstStage = active.stages[0]?.id;
    setBusyId("new");
    try {
      const deal = await api.crm.createDeal({
        pipeline_id: active.id,
        stage_id: firstStage,
        title: newTitle.trim(),
        value: Number(newValue) || 0,
      });
      setDeals((prev) => [deal, ...prev]);
      setNewTitle("");
      setNewValue("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create deal.");
    } finally {
      setBusyId(null);
    }
  };

  const openStages = active?.stages.filter((s) => !s.is_won && !s.is_lost) ?? [];

  return (
    <div className="space-y-5" data-testid="crm-board">
      <SectionHeading
        eyebrow="CRM"
        heading="Sales pipeline"
        description="Track every deal from first touch to close, with AI-recommended next actions."
        action={
          pipelines.length > 1 ? (
            <select
              value={activeId ?? ""}
              onChange={(e) => setActiveId(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              data-testid="crm-pipeline-select"
            >
              {pipelines.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          ) : undefined
        }
      />

      {error && (
        <Surface state="bad" padding="compact" className="text-sm text-bad">{error}</Surface>
      )}

      {/* KPIs */}
      {loading ? (
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}
        </div>
      ) : analytics ? (
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Kpi label="Pipeline value" value={money(analytics.pipeline_value)} />
          <Kpi label="Weighted forecast" value={money(analytics.weighted_forecast)} />
          <Kpi label="Won value" value={money(analytics.won_value)} />
          <Kpi label="Win rate" value={`${Math.round(analytics.win_rate * 100)}%`} />
          <Kpi label="Avg deal size" value={money(analytics.avg_deal_size)} />
          <Kpi label="Open deals" value={String(analytics.open_deals)} />
        </div>
      ) : null}

      {/* Quick add */}
      {active && (
        <div className="flex flex-wrap items-end gap-2">
          <Input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="New deal title…"
            className="w-56"
            data-testid="crm-new-title"
          />
          <Input
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            placeholder="Value"
            type="number"
            className="w-28"
          />
          <Button size="sm" onClick={() => void addDeal()} disabled={busyId === "new" || !newTitle.trim()}>
            <Plus className="h-4 w-4" />
            Add deal
          </Button>
        </div>
      )}

      {/* Board */}
      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-2" data-testid="crm-columns">
          {openStages.map((stage) => {
            const col = deals.filter((d) => d.stage_id === stage.id && d.status === "open");
            const colValue = col.reduce((s, d) => s + Number(d.value), 0);
            return (
              <div key={stage.id} className="w-72 shrink-0 space-y-2">
                <div className="flex items-center justify-between px-1">
                  <span className="text-sm font-medium">{stage.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {col.length} · {money(colValue)}
                  </span>
                </div>
                <div className="space-y-2">
                  {col.map((deal) => (
                    <Surface key={deal.id} padding="compact" className="space-y-2" data-testid="crm-deal-card">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-sm font-medium">{deal.title}</span>
                        <StatusPill tone={PRIORITY_TONE[deal.priority]} size="sm">
                          {deal.priority}
                        </StatusPill>
                      </div>
                      {deal.company && (
                        <p className="text-xs text-muted-foreground">{deal.company}</p>
                      )}
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium">{money(Number(deal.value), deal.currency)}</span>
                        {deal.probability != null && (
                          <span className="text-muted-foreground">{deal.probability}%</span>
                        )}
                      </div>

                      {deal.ai_next_action && (
                        <Surface state="ai" padding="compact" className="space-y-1">
                          <p className="flex items-center gap-1 text-xs font-medium">
                            <Sparkles className="h-3 w-3" /> Next action
                          </p>
                          <p className="text-xs">{deal.ai_next_action.recommendation}</p>
                          <div className="flex gap-1">
                            <StatusPill tone="good" size="sm">
                              {deal.ai_next_action.confidence}% conf
                            </StatusPill>
                            <StatusPill tone="watch" size="sm">
                              risk {deal.ai_next_action.risk_score}
                            </StatusPill>
                          </div>
                        </Surface>
                      )}

                      <div className="flex flex-wrap items-center gap-1">
                        <select
                          value={deal.stage_id ?? ""}
                          onChange={(e) => void move(deal, e.target.value)}
                          disabled={busyId === deal.id}
                          className="h-7 rounded border border-input bg-background px-1 text-xs"
                          aria-label="Move to stage"
                          data-testid="crm-move-select"
                        >
                          {active?.stages.map((s) => (
                            <option key={s.id} value={s.id}>{s.name}</option>
                          ))}
                        </select>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busyId === deal.id}
                          onClick={() => void runNextAction(deal)}
                          title="AI next action"
                        >
                          <TrendingUp className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </Surface>
                  ))}
                  {col.length === 0 && (
                    <p className="px-1 text-xs text-muted-foreground">No deals</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
