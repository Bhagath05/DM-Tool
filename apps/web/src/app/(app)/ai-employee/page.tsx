"use client";

/**
 * AI Employee workspace — the flagship view of what your AI marketer is
 * doing right now.
 *
 * This is a PURE COMPOSER. Every section reads an engine that already
 * shipped server-side and had no frontend until now:
 *
 *   Today's plan          → GET /planner/today
 *   Next move / lifecycle → GET /orchestrator/plan
 *   Work queue            → GET /operations/work  (+ PATCH …/work/{id})
 *   Recent decisions      → GET /decisions
 *   Notifications         → GET /operations/notifications
 *   Marketing health      → the existing MarketingHealthCard component
 *
 * No calculations, no new endpoints, no duplicated logic. Every section
 * degrades independently — one engine being off or cold must never blank
 * the page (several are feature-flagged or need a warm profile).
 *
 * Voice: this reads as an employee talking to the owner. The engines
 * already return plain-language `why` / `rationale` / `reasoning`, so we
 * surface those verbatim rather than inventing marketing copy.
 */

import {
  Brain,
  CheckCircle2,
  Inbox,
  Lightbulb,
  ListTodo,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonLines } from "@/components/ui/skeleton";
import {
  api,
  type DailyPlanResponse,
  type DecisionReportResponse,
  type OpsNotification,
  type OrchestratorPlan,
  type WorkList,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import { MarketingHealthCard } from "../today/_components/marketing-health";
import { WorkCard } from "./_components/work-queue";

export const dynamic = "force-dynamic";

/** Settle a promise into a value or null — one cold engine must never blank
 *  the page. Also catches synchronous throws. */
async function soft<T>(fn: () => Promise<T>): Promise<T | null> {
  try {
    return await fn();
  } catch {
    return null;
  }
}

export default function AiEmployeePage() {
  const [loading, setLoading] = useState(true);
  const [plan, setPlan] = useState<DailyPlanResponse | null>(null);
  const [orch, setOrch] = useState<OrchestratorPlan | null>(null);
  const [work, setWork] = useState<WorkList | null>(null);
  const [decisions, setDecisions] = useState<DecisionReportResponse | null>(null);
  const [notes, setNotes] = useState<OpsNotification[]>([]);

  const loadWork = useCallback(async () => {
    setWork(await soft(() => api.operations.work()));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const [p, o, w, d, n] = await Promise.all([
      soft(() => api.planner.today()),
      soft(() => api.orchestrator.plan()),
      soft(() => api.operations.work()),
      soft(() => api.decisions.get()),
      soft(() => api.operations.notifications()),
    ]);
    setPlan(p);
    setOrch(o);
    setWork(w);
    setDecisions(d);
    setNotes(n?.items ?? []);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <SkeletonLines lines={10} />;

  const items = work?.items ?? [];
  const awaiting = items.filter((i) => i.requires_approval && i.status === "pending");
  const working = items.filter(
    (i) => i.status === "approved" || i.status === "running",
  );
  const upcoming = items.filter((i) => i.scheduled_for && i.status === "pending");
  const done = items.filter((i) => i.status === "completed");
  const nothingYet = !plan && !orch && items.length === 0 && !decisions;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6" data-testid="ai-employee">
      <SectionHeading
        eyebrow="Your AI marketer"
        heading="Here's what I'm working on"
        description="I check your business every day, decide what matters most, and get it ready. Nothing goes out until you say so."
        size="lg"
      />

      {nothingYet && (
        <EmptyState
          icon={Brain}
          title="I'm still getting to know your business"
          description="Once I've learned about your business and had a day to watch what's happening, I'll have a plan for you here."
          action={
            <Link
              href={"/brand-brain/discover" as never}
              className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              Help me learn about your business
            </Link>
          }
        />
      )}

      {/* The single next move — the employee's headline. */}
      {orch?.summary && (
        <section className="rounded-xl border border-ai-border bg-ai-soft p-4">
          <p className="flex items-start gap-2 text-sm text-ai-soft-foreground">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{orch.summary}</span>
          </p>
          {orch.next_action && (
            <div className="mt-3 rounded-lg bg-background/60 p-3">
              <p className="text-sm font-medium">{orch.next_action.action}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {orch.next_action.why}
              </p>
              <Link
                href={orch.next_action.link as never}
                className="mt-1.5 inline-block text-xs font-medium text-primary underline-offset-4 hover:underline"
              >
                Take me there
              </Link>
            </div>
          )}
          {orch.autonomy_note && (
            <p className="mt-2 text-[11px] text-ai-soft-foreground/80">
              {orch.autonomy_note}
            </p>
          )}
        </section>
      )}

      {/* Today's plan */}
      {plan?.plan?.tasks?.length ? (
        <Panel
          icon={ListTodo}
          title="Today's plan"
          hint={plan.plan.focus || plan.plan.summary}
        >
          <ul className="flex flex-col gap-2">
            {plan.plan.tasks.map((t) => (
              <li
                key={t.title}
                className="rounded-lg border border-border p-3"
                data-testid="planned-task"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium">{t.title}</p>
                  <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] capitalize text-muted-foreground">
                    {t.effort}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{t.why}</p>
                {t.suggested_action && (
                  <p className="mt-1 text-[11px] text-muted-foreground/80">
                    Where: {t.suggested_action}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {/* Waiting for approval */}
      {awaiting.length > 0 && (
        <Panel
          icon={Inbox}
          title="Waiting for your OK"
          hint="I've prepared these. They won't go anywhere until you approve."
        >
          <ul className="flex flex-col gap-2">
            {awaiting.map((i) => (
              <WorkCard key={i.id} item={i} onChanged={loadWork} />
            ))}
          </ul>
        </Panel>
      )}

      {/* Working on */}
      {working.length > 0 && (
        <Panel icon={Sparkles} title="I'm working on" hint="Approved and in progress.">
          <ul className="flex flex-col gap-2">
            {working.map((i) => (
              <WorkCard key={i.id} item={i} onChanged={loadWork} />
            ))}
          </ul>
        </Panel>
      )}

      {/* Upcoming */}
      {upcoming.length > 0 && (
        <Panel icon={ListTodo} title="Coming up" hint="Scheduled for later.">
          <ul className="flex flex-col gap-2">
            {upcoming.map((i) => (
              <WorkCard key={i.id} item={i} onChanged={loadWork} />
            ))}
          </ul>
        </Panel>
      )}

      {/* Health — reuses the existing card, not a second copy. */}
      <MarketingHealthCard />

      {/* Recent decisions */}
      {decisions?.report?.decisions?.length ? (
        <Panel
          icon={Lightbulb}
          title="What I decided, and why"
          hint={decisions.report.data_sufficiency}
        >
          <ul className="flex flex-col gap-2">
            {decisions.report.decisions.map((d) => (
              <li
                key={d.decision}
                className="rounded-lg border border-border p-3"
                data-testid="decision"
              >
                <p className="text-sm font-medium">{d.decision}</p>
                <p className="mt-1 text-xs text-muted-foreground">{d.reasoning}</p>
                {d.evidence.length > 0 && (
                  <ul className="mt-1.5 flex list-disc flex-col gap-0.5 pl-4 text-[11px] text-muted-foreground">
                    {d.evidence.slice(0, 3).map((e) => (
                      <li key={e}>{e}</li>
                    ))}
                  </ul>
                )}
                <p className="mt-2 rounded-md bg-good-soft px-2.5 py-1.5 text-xs text-good-soft-foreground">
                  <span className="font-medium">If you do this: </span>
                  {d.expected_impact}
                </p>
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  How sure I am: {d.confidence}% · Helps with: {d.business_objective}
                </p>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {/* Completed */}
      {done.length > 0 && (
        <Panel icon={CheckCircle2} title="Done" hint="Finished recently.">
          <ul className="flex flex-col gap-1.5">
            {done.map((i) => (
              <li key={i.id} className="flex items-center gap-2 text-sm">
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-good" />
                <span className="truncate text-muted-foreground">{i.title}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {/* Notifications */}
      {notes.length > 0 && (
        <Panel icon={Inbox} title="Things you should know" hint="Recent alerts.">
          <ul className="flex flex-col gap-1.5">
            {notes.slice(0, 6).map((n) => (
              <li key={n.id} className="rounded-lg border border-border p-2.5">
                <p className={cn("text-sm", !n.read && "font-medium")}>{n.title}</p>
                {n.body && (
                  <p className="text-xs text-muted-foreground">{n.body}</p>
                )}
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function Panel({
  icon: Icon,
  title,
  hint,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border bg-background p-4 sm:p-5">
      <div className="mb-3 flex items-start gap-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Icon className="h-3.5 w-3.5" />
        </span>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{title}</h2>
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}
