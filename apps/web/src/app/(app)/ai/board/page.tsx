"use client";

/**
 * Marketing Board — makes the Marketing Brain's work visible and understandable.
 *
 * It is a VIEW over real backend state, not a new task system: it reuses the
 * operations work queue (`api.operations.work`) and the consequential-approval
 * requests (`api.agentActions.list`). It answers, for a non-technical owner:
 * what is DM Tool doing, what's happening now, what needs me, what's next, and
 * what's closed out.
 *
 * Safety: the browser never executes a consequential external action from here.
 * Approving a *work* item is the existing safe workflow PATCH (sets state; the
 * operations loop still gates execution by policy + master switch). A proposed
 * *consequential* action is never acted on here — it links to /ai/approvals,
 * which runs the Phase-4A approval boundary. Nothing is fabricated; empty state
 * is shown when there's no work.
 */

import { AlertTriangle, Inbox, LayoutGrid, List as ListIcon, CalendarClock } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { GenBlock } from "@/components/brain/blocks";
import { BrainTabs } from "@/components/brain/brain-tabs";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonLines } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { api, type ApprovalView, type WorkItem } from "@/lib/api";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

// A friendly marketing lifecycle, each column derived from REAL backend state.
type ColumnKey = "ideas" | "needs_you" | "approved" | "scheduled" | "live" | "closed";

const COLUMNS: { key: ColumnKey; label: string; hint: string }[] = [
  { key: "ideas", label: "Ideas", hint: "Proposed by the Brain" },
  { key: "needs_you", label: "Needs you", hint: "Waiting on your decision" },
  { key: "approved", label: "Approved", hint: "Cleared to run" },
  { key: "scheduled", label: "Scheduled", hint: "Queued to go out" },
  { key: "live", label: "Live", hint: "Done / running" },
  { key: "closed", label: "Closed", hint: "Dismissed or ended" },
];

type View = "board" | "list" | "timeline";

interface BoardCard {
  id: string;
  source: "work" | "approval";
  typeLabel: string;
  title: string;
  column: ColumnKey;
  status: string;
  priority?: string;
  why?: string;
  expectedEffect?: string;
  requiresApproval: boolean;
  scheduledFor?: string | null;
  createdAt: string;
  approvalId?: string;
  work?: WorkItem;
  approval?: ApprovalView;
}

const WORK_TYPE_LABEL: Record<string, string> = {
  content_generation: "Content",
  blog: "Content",
  campaign_update: "Campaign",
  budget_change: "Budget",
  reel: "Creative",
  ad: "Ad",
  email: "Email",
  weekly_report: "Report",
};

function workColumn(status: string): ColumnKey {
  switch (status) {
    case "proposed":
      return "ideas";
    case "awaiting_approval":
      return "needs_you";
    case "approved":
      return "approved";
    case "queued":
      return "scheduled";
    case "executed":
      return "live";
    default:
      return "closed"; // dismissed | failed | anything unknown
  }
}

function approvalColumn(status: string): ColumnKey {
  switch (status) {
    case "pending":
      return "needs_you";
    case "approved":
      return "approved";
    case "executed":
      return "live";
    default:
      return "closed"; // rejected | expired | failed
  }
}

function approvalTypeLabel(tool: string): string {
  if (tool.includes("publish")) return "Publish";
  return "Action";
}

const STATUS_TONE: Record<string, PillTone> = {
  ideas: "muted",
  needs_you: "watch",
  approved: "ai",
  scheduled: "ai",
  live: "good",
  closed: "muted",
};

// Static dot classes (Tailwind can't see dynamically-built class names).
const DOT_CLASS: Record<ColumnKey, string> = {
  ideas: "bg-muted-foreground",
  needs_you: "bg-watch",
  approved: "bg-ai",
  scheduled: "bg-ai",
  live: "bg-good",
  closed: "bg-muted-foreground",
};

function cardFromWork(w: WorkItem): BoardCard {
  return {
    id: `work-${w.id}`,
    source: "work",
    typeLabel: WORK_TYPE_LABEL[w.kind] ?? "Work",
    title: w.title,
    column: workColumn(w.status),
    status: w.status,
    priority: w.priority,
    why: w.rationale,
    requiresApproval: w.requires_approval,
    scheduledFor: w.scheduled_for,
    createdAt: w.created_at,
    work: w,
  };
}

function cardFromApproval(a: ApprovalView): BoardCard {
  return {
    id: `appr-${a.id}`,
    source: "approval",
    typeLabel: approvalTypeLabel(a.tool_name),
    title: a.reason || a.tool_name,
    column: approvalColumn(a.status),
    status: a.status,
    why: a.reason ?? undefined,
    expectedEffect: a.expected_effect ?? undefined,
    requiresApproval: true,
    createdAt: a.created_at,
    approvalId: a.id,
    approval: a,
  };
}

export default function MarketingBoardPage() {
  const [cards, setCards] = useState<BoardCard[] | null>(null);
  const [error, setError] = useState(false);
  const [view, setView] = useState<View>("board");
  const [needsMeOnly, setNeedsMeOnly] = useState(false);
  const [selected, setSelected] = useState<BoardCard | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(false);
    try {
      // Fetch both real sources; tolerate one being unavailable.
      const [work, approvals] = await Promise.all([
        api.operations.work().catch(() => ({ items: [] as WorkItem[], awaiting_approval: 0 })),
        api.agentActions.list().catch(() => ({ items: [] as ApprovalView[] })),
      ]);
      const next = [
        ...work.items.map(cardFromWork),
        ...approvals.items.map(cardFromApproval),
      ].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
      setCards(next);
    } catch {
      setError(true);
      setCards([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    const list = cards ?? [];
    return needsMeOnly ? list.filter((c) => c.column === "needs_you") : list;
  }, [cards, needsMeOnly]);

  const needsMeCount = (cards ?? []).filter((c) => c.column === "needs_you").length;

  const approveWork = useCallback(
    async (card: BoardCard, decision: "approved" | "dismissed") => {
      if (!card.work) return;
      setBusyId(card.id);
      setActionError(null);
      try {
        await api.operations.updateWork(card.work.id, decision);
        setSelected(null);
        await load();
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "That change could not be saved.");
      } finally {
        setBusyId(null);
      }
    },
    [load],
  );

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col gap-5" data-testid="board">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionHeading
          eyebrow="Marketing Brain"
          heading="The board"
          description="Everything your AI marketer is working on — what's happening, what needs you, and what's next. The Brain prepares the work; you stay in control."
        />
        <BrainTabs active="board" />
      </div>

      {/* Controls. */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex items-center gap-1 rounded-lg border border-border bg-card p-0.5" role="tablist" aria-label="View">
          {([
            ["board", "Board", LayoutGrid],
            ["list", "List", ListIcon],
            ["timeline", "Timeline", CalendarClock],
          ] as const).map(([key, label, Icon]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={view === key}
              onClick={() => setView(key)}
              data-testid={`board-view-${key}`}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                view === key ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted",
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setNeedsMeOnly((v) => !v)}
          aria-pressed={needsMeOnly}
          data-testid="board-needs-me"
          className={cn(
            "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
            needsMeOnly
              ? "border-watch-border bg-watch-soft text-watch-soft-foreground"
              : "border-border text-muted-foreground hover:bg-muted",
          )}
        >
          <Inbox className="h-3.5 w-3.5" />
          Needs me
          {needsMeCount > 0 && (
            <span className="tabular rounded-full bg-watch px-1.5 text-[10px] font-semibold text-white">
              {needsMeCount}
            </span>
          )}
        </button>
      </div>

      {/* Body. */}
      {cards === null ? (
        <div className="flex gap-4" data-testid="board-loading">
          {[0, 1, 2].map((i) => (
            <div key={i} className="w-64 shrink-0">
              <SkeletonLines lines={5} />
            </div>
          ))}
        </div>
      ) : error ? (
        <EmptyState
          icon={AlertTriangle}
          title="Couldn't load the board"
          description="Give it a moment and refresh — nothing was changed."
        />
      ) : visible.length === 0 ? (
        <EmptyState
          icon={LayoutGrid}
          title={needsMeOnly ? "Nothing needs you right now" : "No work on the board yet"}
          description={
            needsMeOnly
              ? "When something needs your approval or input, it'll show up here."
              : "As your AI marketer plans and prepares work, it'll appear here so you can follow along."
          }
        />
      ) : view === "board" ? (
        <BoardColumns cards={visible} onOpen={setSelected} />
      ) : view === "list" ? (
        <BoardList cards={visible} onOpen={setSelected} />
      ) : (
        <BoardTimeline cards={visible} onOpen={setSelected} />
      )}

      <DetailPanel
        card={selected}
        busy={busyId !== null}
        error={actionError}
        onClose={() => {
          setSelected(null);
          setActionError(null);
        }}
        onApprove={(c) => approveWork(c, "approved")}
        onDismiss={(c) => approveWork(c, "dismissed")}
      />
    </div>
  );
}

function TypeBadge({ card }: { card: BoardCard }) {
  return (
    <span className="rounded-md border border-border bg-background/60 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
      {card.typeLabel}
    </span>
  );
}

function CardTile({ card, onOpen }: { card: BoardCard; onOpen: (c: BoardCard) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(card)}
      data-testid="board-card"
      className="flex w-full flex-col gap-2 rounded-lg border border-border bg-card p-3 text-left transition-colors hover:border-ai-border"
    >
      <div className="flex items-center justify-between gap-2">
        <TypeBadge card={card} />
        <span className="text-[10px] font-medium text-ai">AI</span>
      </div>
      <p className="line-clamp-2 text-sm font-medium">{card.title}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        {card.requiresApproval && card.column === "needs_you" && (
          <StatusPill tone="watch">Needs you</StatusPill>
        )}
        {card.priority && card.priority !== "medium" && (
          <span className="text-[11px] capitalize text-muted-foreground">{card.priority} priority</span>
        )}
      </div>
    </button>
  );
}

function BoardColumns({ cards, onOpen }: { cards: BoardCard[]; onOpen: (c: BoardCard) => void }) {
  const [focus, setFocus] = useState<ColumnKey>("needs_you");
  const byColumn = (key: ColumnKey) => cards.filter((c) => c.column === key);
  return (
    <>
      {/* Mobile: focused-column selector (never squeeze all columns). */}
      <div className="flex gap-1.5 overflow-x-auto md:hidden" data-testid="board-mobile-columns">
        {COLUMNS.map((col) => (
          <button
            key={col.key}
            type="button"
            onClick={() => setFocus(col.key)}
            className={cn(
              "shrink-0 rounded-md px-2.5 py-1 text-xs font-medium",
              focus === col.key ? "bg-foreground text-background" : "bg-muted text-muted-foreground",
            )}
          >
            {col.label} · {byColumn(col.key).length}
          </button>
        ))}
      </div>
      <div className="md:hidden">
        <Column col={COLUMNS.find((c) => c.key === focus)!} cards={byColumn(focus)} onOpen={onOpen} />
      </div>

      {/* Desktop/tablet: horizontally scrollable columns. */}
      <div className="scrollbar-clean hidden gap-4 overflow-x-auto pb-2 md:flex" data-testid="board-columns">
        {COLUMNS.map((col) => (
          <div key={col.key} className="w-64 shrink-0">
            <Column col={col} cards={byColumn(col.key)} onOpen={onOpen} />
          </div>
        ))}
      </div>
    </>
  );
}

function Column({
  col,
  cards,
  onOpen,
}: {
  col: { key: ColumnKey; label: string; hint: string };
  cards: BoardCard[];
  onOpen: (c: BoardCard) => void;
}) {
  return (
    <section data-testid={`board-column-${col.key}`} className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span aria-hidden className={cn("h-2 w-2 rounded-full", DOT_CLASS[col.key])} />
          <span className="text-xs font-semibold">{col.label}</span>
          <span className="tabular text-[11px] text-muted-foreground">{cards.length}</span>
        </div>
      </div>
      <p className="text-[11px] text-muted-foreground">{col.hint}</p>
      <div className="flex flex-col gap-2">
        {cards.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-[11px] text-muted-foreground">
            Nothing here
          </p>
        ) : (
          cards.map((c) => <CardTile key={c.id} card={c} onOpen={onOpen} />)
        )}
      </div>
    </section>
  );
}

function BoardList({ cards, onOpen }: { cards: BoardCard[]; onOpen: (c: BoardCard) => void }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border" data-testid="board-list">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="px-3 py-2 font-semibold">Type</th>
            <th className="px-3 py-2 font-semibold">Title</th>
            <th className="px-3 py-2 font-semibold">Stage</th>
            <th className="px-3 py-2 font-semibold">Priority</th>
          </tr>
        </thead>
        <tbody>
          {cards.map((c) => (
            <tr
              key={c.id}
              className="cursor-pointer border-b border-border last:border-0 hover:bg-muted/40"
              onClick={() => onOpen(c)}
              data-testid="board-list-row"
            >
              <td className="px-3 py-2"><TypeBadge card={c} /></td>
              <td className="px-3 py-2">{c.title}</td>
              <td className="px-3 py-2">
                <StatusPill tone={STATUS_TONE[c.column] ?? "neutral"}>
                  {COLUMNS.find((col) => col.key === c.column)?.label ?? c.column}
                </StatusPill>
              </td>
              <td className="px-3 py-2 capitalize text-muted-foreground">{c.priority ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BoardTimeline({ cards, onOpen }: { cards: BoardCard[]; onOpen: (c: BoardCard) => void }) {
  const dated = cards
    .filter((c) => c.scheduledFor)
    .sort((a, b) => (a.scheduledFor! < b.scheduledFor! ? -1 : 1));
  const undated = cards.filter((c) => !c.scheduledFor);
  return (
    <div className="flex flex-col gap-4" data-testid="board-timeline">
      {dated.length === 0 ? (
        <p className="text-sm text-muted-foreground">No scheduled dates yet — items appear here once they have a planned time.</p>
      ) : (
        <ol className="flex flex-col">
          {dated.map((c) => (
            <li key={c.id} className="flex gap-3 pb-3">
              <div className="flex flex-col items-center">
                <span aria-hidden className="mt-1.5 h-2 w-2 rounded-full bg-ai" />
                <span aria-hidden className="w-px flex-1 bg-border" />
              </div>
              <button type="button" onClick={() => onOpen(c)} className="min-w-0 text-left">
                <p className="text-xs text-muted-foreground">
                  {new Date(c.scheduledFor!).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </p>
                <p className="text-sm font-medium">{c.title}</p>
              </button>
            </li>
          ))}
        </ol>
      )}
      {undated.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {undated.length} item{undated.length === 1 ? "" : "s"} without a scheduled time (see Board or List).
        </p>
      )}
    </div>
  );
}

function DetailPanel({
  card,
  busy,
  error,
  onClose,
  onApprove,
  onDismiss,
}: {
  card: BoardCard | null;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onApprove: (c: BoardCard) => void;
  onDismiss: (c: BoardCard) => void;
}) {
  const open = card !== null;
  const stageLabel = card ? COLUMNS.find((c) => c.key === card.column)?.label ?? card.column : "";
  const canDecideWork = card?.source === "work" && (card.status === "awaiting_approval" || card.status === "proposed");
  return (
    <Modal open={open} onOpenChange={(o) => !o && onClose()} title={card?.title}>
      {card && (
        <div className="flex flex-col gap-3" data-testid="board-detail">
          <div className="flex items-center gap-2">
            <TypeBadge card={card} />
            <StatusPill tone={STATUS_TONE[card.column] ?? "neutral"}>{stageLabel}</StatusPill>
            <span className="text-[11px] text-muted-foreground">Prepared by your AI marketer</span>
          </div>

          {card.why && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">Why the Brain prepared this</p>
              <p className="mt-0.5 text-sm">{card.why}</p>
            </div>
          )}
          {card.expectedEffect && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">Expected effect</p>
              <p className="mt-0.5 text-sm">{card.expectedEffect}</p>
            </div>
          )}
          {card.scheduledFor && (
            <p className="text-sm text-muted-foreground">
              Scheduled for {new Date(card.scheduledFor).toLocaleString()}
            </p>
          )}

          {/* A consequential approval is NEVER acted on here — it routes to the
              server-enforced approval surface. */}
          {card.source === "approval" && card.approvalId && (
            <GenBlock eyebrow="Approval required" accent>
              <p className="text-sm">
                This is a consequential action the Brain proposed. Nothing has run. Review and decide on
                the approvals surface.
              </p>
              <a
                href="/ai/approvals"
                className="mt-2 inline-block rounded-lg border border-ai-border px-3 py-1.5 text-xs font-medium hover:bg-ai-soft"
              >
                Review &amp; decide →
              </a>
            </GenBlock>
          )}

          {error && <p className="text-sm text-bad" data-testid="board-detail-error">{error}</p>}

          {/* Safe workflow decision for AI work items (sets state; does not
              publish — the operations loop still gates execution). */}
          {canDecideWork && (
            <div className="mt-1 flex justify-end gap-2">
              <Button variant="outline" size="sm" disabled={busy} onClick={() => onDismiss(card)} data-testid="board-dismiss">
                Dismiss
              </Button>
              <Button size="sm" disabled={busy} onClick={() => onApprove(card)} data-testid="board-approve">
                {busy ? "Saving…" : "Approve"}
              </Button>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
