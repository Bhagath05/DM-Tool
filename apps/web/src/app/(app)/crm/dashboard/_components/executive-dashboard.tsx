"use client";

/**
 * Phase 6.5 Slice 6 — Executive CRM Dashboard.
 *
 * The command center over the live /crm/dashboard aggregation (which reuses the
 * existing pipeline analytics, email stats, and AI-assistant insights). KPI
 * cards, pipeline funnel, risk distribution, rep leaderboard, forecast, activity
 * counts, AI insight cards, stalled deals, and CSV export. Dependency-free
 * charts; design system reused.
 */

import { AlertTriangle, Download, Sparkles, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { Surface } from "@/components/ui/surface";
import { api, type CrmExecutiveDashboard, type CrmPipeline } from "@/lib/api";
import { money, pct } from "@/lib/crm-format";

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Surface padding="compact" className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-lg font-semibold">{value}</span>
      {sub && <span className="text-[11px] text-muted-foreground">{sub}</span>}
    </Surface>
  );
}

function Bar({ label, value, max, tone = "neutral", right }: { label: string; value: number; max: number; tone?: PillTone; right?: string }) {
  const w = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  const bg = tone === "good" ? "bg-good" : tone === "bad" ? "bg-bad" : tone === "watch" ? "bg-watch" : "bg-primary";
  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between text-xs">
        <span className="truncate">{label}</span>
        <span className="text-muted-foreground">{right}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div className={`h-full ${bg}`} style={{ width: `${w}%` }} />
      </div>
    </div>
  );
}

const RISK_TONE: Record<string, PillTone> = { high: "good", medium: "watch", low: "bad" };
const CONF_TONE = (c: number): PillTone => (c >= 80 ? "good" : c >= 60 ? "watch" : "muted");

export function ExecutiveDashboard() {
  const [data, setData] = useState<CrmExecutiveDashboard | null>(null);
  const [pipelines, setPipelines] = useState<CrmPipeline[]>([]);
  const [pipelineId, setPipelineId] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.crm.dashboard({ pipeline_id: pipelineId || undefined, owner_user_id: ownerId || undefined }));
    } finally {
      setLoading(false);
    }
  }, [pipelineId, ownerId]);

  useEffect(() => {
    void api.crm.pipelines().then(setPipelines).catch(() => {});
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const owners = useMemo(() => data?.reps.map((r) => r.owner_user_id) ?? [], [data]);
  const funnelMax = useMemo(() => Math.max(1, ...(data?.pipeline.funnel.map((s) => s.count) ?? [1])), [data]);
  const repMax = useMemo(() => Math.max(1, ...(data?.reps.map((r) => r.revenue) ?? [1])), [data]);
  const fcMax = useMemo(() => Math.max(1, ...(data?.forecast.monthly.map((m) => m.won_revenue) ?? [1])), [data]);

  const k = data?.kpis;

  return (
    <div className="space-y-5" data-testid="exec-dashboard">
      <SectionHeading
        eyebrow="CRM" heading="Executive Dashboard"
        description="Your whole sales operation at a glance — pipeline, forecast, team, and AI insights, all from live CRM data."
        action={
          <div className="flex flex-wrap items-center gap-2">
            <select value={pipelineId} onChange={(e) => setPipelineId(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm" data-testid="dash-pipeline">
              <option value="">All pipelines</option>
              {pipelines.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            {owners.length > 0 && (
              <select value={ownerId} onChange={(e) => setOwnerId(e.target.value)}
                className="h-9 rounded-md border border-input bg-background px-2 text-sm" data-testid="dash-owner">
                <option value="">All reps</option>
                {owners.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            )}
            <a href={api.crm.dashboardExportUrl({ pipeline_id: pipelineId || undefined, owner_user_id: ownerId || undefined })}>
              <Button size="sm" variant="outline"><Download className="h-4 w-4" /> CSV</Button>
            </a>
          </div>
        }
      />

      {loading || !k ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        <>
          {/* KPI grid */}
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Kpi label="Revenue (won)" value={money(k.revenue)} sub={`${k.won_deals} deals`} />
            <Kpi label="Pipeline value" value={money(k.pipeline_value)} sub={`${k.active_opportunities} open`} />
            <Kpi label="Weighted forecast" value={money(data.forecast.pipeline_weighted_forecast)} />
            <Kpi label="Win rate" value={pct(k.win_rate)} />
            <Kpi label="Avg deal size" value={money(k.avg_deal_size)} />
            <Kpi label="Sales velocity" value={money(k.sales_velocity)} sub="/day" />
            <Kpi label="Total leads" value={String(k.total_leads)} sub={`${k.qualified_leads} qualified`} />
            <Kpi label="Sales cycle" value={k.avg_sales_cycle_days != null ? `${k.avg_sales_cycle_days}d` : "—"} />
            <Kpi label="Email open rate" value={pct(k.email_open_rate)} />
            <Kpi label="Email reply rate" value={pct(k.email_reply_rate)} />
            <Kpi label="Meetings done" value={String(k.meetings_completed)} />
            <Kpi label="Follow-up compliance" value={k.follow_up_compliance != null ? pct(k.follow_up_compliance) : "—"} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Pipeline funnel */}
            <Surface padding="compact" className="space-y-3">
              <p className="text-sm font-medium">Pipeline funnel</p>
              {data.pipeline.funnel.length === 0 ? (
                <p className="text-xs text-muted-foreground">No open deals.</p>
              ) : data.pipeline.funnel.map((s) => (
                <Bar key={s.stage_id ?? s.stage_name} label={s.stage_name} value={s.count} max={funnelMax}
                  right={`${s.count} · ${money(s.value)}${s.avg_days_in_stage != null ? ` · ${s.avg_days_in_stage}d` : ""}`} />
              ))}
            </Surface>

            {/* Risk distribution */}
            <Surface padding="compact" className="space-y-3">
              <p className="text-sm font-medium">Deal risk distribution</p>
              {data.pipeline.risk_distribution.map((r) => (
                <Bar key={r.band} label={`${r.band} probability`} value={r.count}
                  max={Math.max(1, ...data.pipeline.risk_distribution.map((x) => x.count))}
                  tone={RISK_TONE[r.band]} right={`${r.count} · ${money(r.value)}`} />
              ))}
            </Surface>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Revenue forecast */}
            <Surface padding="compact" className="space-y-3">
              <p className="text-sm font-medium">Won revenue by month</p>
              {data.forecast.monthly.length === 0 ? (
                <p className="text-xs text-muted-foreground">No closed-won revenue yet.</p>
              ) : [...data.forecast.monthly].reverse().map((m) => (
                <Bar key={m.period} label={m.period} value={m.won_revenue} max={fcMax}
                  tone="good" right={`${money(m.won_revenue)} · ${m.deals}`} />
              ))}
            </Surface>

            {/* Activity */}
            <Surface padding="compact" className="space-y-2">
              <p className="text-sm font-medium">Activity</p>
              <div className="grid grid-cols-3 gap-2 text-center">
                {([["Calls", data.activity.calls], ["Meetings", data.activity.meetings], ["Emails", data.activity.emails],
                   ["Notes", data.activity.notes], ["Tasks open", data.activity.tasks_open], ["Follow-ups due", data.activity.follow_ups_due]] as [string, number][])
                  .map(([label, v]) => (
                    <div key={label} className="rounded-md border border-border p-2">
                      <p className="text-lg font-semibold">{v}</p>
                      <p className="text-[11px] text-muted-foreground">{label}</p>
                    </div>
                  ))}
              </div>
            </Surface>
          </div>

          {/* Rep leaderboard */}
          <Surface padding="compact" className="space-y-3">
            <p className="text-sm font-medium">Team leaderboard</p>
            {data.reps.length === 0 ? (
              <p className="text-xs text-muted-foreground">No deals owned yet.</p>
            ) : (
              <div className="space-y-2">
                {data.reps.slice(0, 10).map((r) => (
                  <div key={r.owner_user_id} className="space-y-0.5">
                    <Bar label={r.owner_user_id} value={r.revenue} max={repMax} tone="good"
                      right={`${money(r.revenue)} · ${pct(r.win_rate)} win`} />
                    <p className="text-[11px] text-muted-foreground">
                      {r.won_deals} won · {r.open_deals} open · {r.meetings} mtg · {r.calls} calls · {r.emails} emails · {r.tasks_completed} tasks
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Surface>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Stalled deals */}
            <Surface padding="compact" className="space-y-2">
              <p className="flex items-center gap-1.5 text-sm font-medium">
                <AlertTriangle className="h-4 w-4 text-watch" /> Stalled deals
              </p>
              {data.pipeline.stalled_deals.length === 0 ? (
                <p className="text-xs text-muted-foreground">Nothing stalled — nice.</p>
              ) : data.pipeline.stalled_deals.map((d) => (
                <div key={d.id} className="flex items-center justify-between text-sm">
                  <span className="truncate">{d.title}</span>
                  <span className="text-xs text-muted-foreground">{money(d.value)} · {d.days_inactive}d idle</span>
                </div>
              ))}
              {data.pipeline.lost_reasons.length > 0 && (
                <>
                  <p className="pt-2 text-xs font-medium text-muted-foreground">Top lost reasons</p>
                  {data.pipeline.lost_reasons.slice(0, 5).map((l) => (
                    <div key={l.reason} className="flex justify-between text-xs">
                      <span className="truncate">{l.reason}</span><span className="text-muted-foreground">{l.count}</span>
                    </div>
                  ))}
                </>
              )}
            </Surface>

            {/* AI executive insights */}
            <Surface padding="compact" className="space-y-2">
              <p className="flex items-center gap-1.5 text-sm font-medium">
                <Sparkles className="h-4 w-4" /> AI executive insights
              </p>
              {data.ai_insights.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Generate insights on deals & contacts to surface risks and opportunities here.
                </p>
              ) : data.ai_insights.map((i) => (
                <div key={i.id} className="rounded-md border border-border p-2">
                  <div className="flex items-center gap-2">
                    <StatusPill tone={CONF_TONE(i.confidence)} size="sm">{i.confidence}%</StatusPill>
                    <span className="text-xs text-muted-foreground">{(i.affected_records[0] ?? i.kind)}</span>
                  </div>
                  {i.recommendation && <p className="mt-1 text-sm">{i.recommendation}</p>}
                  {i.expected_outcome && (
                    <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <TrendingUp className="h-3 w-3" /> {i.expected_outcome}
                    </p>
                  )}
                </div>
              ))}
            </Surface>
          </div>

          <p className="text-[11px] text-muted-foreground">
            Generated {new Date(data.generated_at).toLocaleString()} · all figures from live CRM data.
          </p>
        </>
      )}
    </div>
  );
}
