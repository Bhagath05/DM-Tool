"use client";

/**
 * Phase 6.5 Slice 3 — CRM Tasks & Calendar.
 *
 * Queue-driven task manager over the live /crm/tasks API: Today / Upcoming /
 * Overdue / Completed / Mine / All, quick-create, complete, a detail drawer with
 * the grounded AI suggestion, filters, search, and an agenda (upcoming grouped
 * by day). Design system reused; responsive.
 */

import {
  Calendar,
  CheckCircle2,
  Clock,
  Plus,
  Repeat,
  Search,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { Surface } from "@/components/ui/surface";
import {
  api,
  type CrmActivityType,
  type CrmTask,
  type CrmTaskPriority,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const QUEUES = ["today", "upcoming", "overdue", "mine", "completed", "all"] as const;
type Queue = (typeof QUEUES)[number];

const PRIORITY_TONE: Record<CrmTaskPriority, PillTone> = {
  low: "muted",
  medium: "neutral",
  high: "watch",
  urgent: "bad",
};

const TYPES: CrmActivityType[] = [
  "follow_up", "call", "meeting", "demo", "email_reminder", "internal", "approval", "custom",
];

function humanize(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function dueTone(task: CrmTask): PillTone {
  if (task.status === "completed") return "good";
  if (!task.due_at) return "neutral";
  const due = new Date(task.due_at).getTime();
  if (due < Date.now()) return "bad";
  if (due < Date.now() + 86_400_000) return "watch";
  return "neutral";
}

// ------------------------------------------------------------ detail drawer
function TaskDrawer({
  taskId,
  onClose,
  onChanged,
}: {
  taskId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [task, setTask] = useState<CrmTask | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => setTask(await api.crm.task(taskId)), [taskId]);
  useEffect(() => {
    void load();
  }, [load]);

  const suggest = async () => {
    setBusy(true);
    try {
      setTask(await api.crm.suggestTask(taskId));
    } finally {
      setBusy(false);
    }
  };

  const complete = async () => {
    setBusy(true);
    try {
      await api.crm.completeTask(taskId);
      onChanged();
      onClose();
    } finally {
      setBusy(false);
    }
  };

  const s = task?.ai_suggestion;

  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={task?.title ?? "Loading…"}
      description={task ? humanize(task.activity_type) : undefined}
      className="max-w-xl" data-testid="task-drawer">
      {!task ? (
        <div className="p-4"><Skeleton className="h-40 w-full" /></div>
      ) : (
        <div className="space-y-4 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill tone={PRIORITY_TONE[task.priority]} size="sm">{task.priority}</StatusPill>
            <StatusPill tone={task.status === "completed" ? "good" : "neutral"} size="sm">
              {humanize(task.status)}
            </StatusPill>
            {task.is_recurring && (
              <StatusPill tone="ai" size="sm"><Repeat className="h-3 w-3" /> recurring</StatusPill>
            )}
            {task.due_at && (
              <StatusPill tone={dueTone(task)} size="sm">
                due {new Date(task.due_at).toLocaleDateString()}
              </StatusPill>
            )}
            {task.source?.startsWith("automation") && (
              <StatusPill tone="muted" size="sm">auto</StatusPill>
            )}
          </div>

          {task.description && <p className="text-sm">{task.description}</p>}

          <div className="flex gap-2">
            {task.status !== "completed" && (
              <Button size="sm" onClick={() => void complete()} disabled={busy}>
                <CheckCircle2 className="h-4 w-4" /> Complete
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => void suggest()} disabled={busy}>
              <Sparkles className="h-4 w-4" /> AI suggest
            </Button>
          </div>

          {s && (
            <Surface state="ai" padding="compact" className="space-y-1 text-sm">
              <p className="font-medium">Next: {s.follow_up}</p>
              <p className="text-xs">
                Suggested {s.recommended_priority} priority · due in {s.recommended_due_in_days}d
              </p>
              {s.risk_alert && s.risk_alert !== "None" && (
                <p className="text-xs text-bad">Risk: {s.risk_alert}</p>
              )}
              <div className="flex items-center gap-2">
                <StatusPill tone="good" size="sm">{s.confidence}% confidence</StatusPill>
                <span className="text-xs text-muted-foreground">{s.reason}</span>
              </div>
            </Surface>
          )}
        </div>
      )}
    </Modal>
  );
}

// ------------------------------------------------------------ board
export function TasksBoard() {
  const [queue, setQueue] = useState<Queue>("today");
  const [typeFilter, setTypeFilter] = useState<CrmActivityType | "">("");
  const [search, setSearch] = useState("");
  const [tasks, setTasks] = useState<CrmTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newType, setNewType] = useState<CrmActivityType>("follow_up");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.crm.tasks({
        queue: queue === "all" ? undefined : queue,
        activity_type: typeFilter || undefined,
        q: search || undefined,
        limit: 200,
      });
      setTasks(r.items);
    } finally {
      setLoading(false);
    }
  }, [queue, typeFilter, search]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 200);
    return () => clearTimeout(t);
  }, [load]);

  const complete = async (task: CrmTask) => {
    setBusyId(task.id);
    try {
      await api.crm.completeTask(task.id);
      void load();
    } finally {
      setBusyId(null);
    }
  };

  const add = async () => {
    if (!newTitle.trim()) return;
    const due = queue === "today" ? new Date().toISOString() : undefined;
    await api.crm.createTask({ title: newTitle.trim(), activity_type: newType, due_at: due });
    setNewTitle("");
    void load();
  };

  // Agenda grouping for upcoming.
  const grouped = useMemo(() => {
    const map = new Map<string, CrmTask[]>();
    for (const t of tasks) {
      const key = t.due_at ? new Date(t.due_at).toLocaleDateString() : "No date";
      const arr = map.get(key) ?? [];
      arr.push(t);
      map.set(key, arr);
    }
    return [...map.entries()];
  }, [tasks]);

  return (
    <div className="space-y-4" data-testid="tasks-board">
      <SectionHeading
        eyebrow="CRM"
        heading="Tasks & Calendar"
        description="Your follow-ups, calls, and meetings — with auto-generated tasks and AI suggestions grounded in your CRM data."
      />

      {/* Queue tabs */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex flex-wrap rounded-md border border-border p-0.5">
          {QUEUES.map((qk) => (
            <button
              key={qk}
              onClick={() => setQueue(qk)}
              className={cn(
                "rounded px-3 py-1 text-sm capitalize",
                queue === qk ? "bg-primary text-primary-foreground" : "text-muted-foreground",
              )}
              data-testid={`task-queue-${qk}`}
            >
              {qk}
            </button>
          ))}
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as CrmActivityType | "")}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
        >
          <option value="">All types</option>
          {TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
        </select>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tasks…" className="h-9 w-48 pl-8" data-testid="task-search" />
        </div>
      </div>

      {/* Quick add */}
      <div className="flex flex-wrap items-center gap-2">
        <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)}
          placeholder="New task…" className="w-56" data-testid="task-new-title"
          onKeyDown={(e) => e.key === "Enter" && void add()} />
        <select value={newType} onChange={(e) => setNewType(e.target.value as CrmActivityType)}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm">
          {TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
        </select>
        <Button size="sm" onClick={() => void add()} disabled={!newTitle.trim()}>
          <Plus className="h-4 w-4" /> Add task
        </Button>
      </div>

      {/* List / agenda */}
      {loading ? (
        <Skeleton className="h-48 w-full" />
      ) : tasks.length === 0 ? (
        <EmptyState icon={queue === "completed" ? CheckCircle2 : Calendar}
          title={`Nothing in ${queue}`}
          description="Create a task above, or let deal & contact automation draft follow-ups for you." />
      ) : (
        <div className="space-y-4">
          {grouped.map(([day, group]) => (
            <div key={day} className="space-y-2">
              {queue !== "completed" && (
                <p className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
                  <Clock className="h-3 w-3" /> {day}
                </p>
              )}
              {group.map((task) => (
                <Surface key={task.id} padding="compact"
                  className="flex items-center gap-3" data-testid="task-row">
                  {task.status !== "completed" && (
                    <button
                      onClick={() => void complete(task)}
                      disabled={busyId === task.id}
                      className="text-muted-foreground hover:text-good"
                      title="Complete"
                      aria-label="Complete task"
                    >
                      <CheckCircle2 className="h-5 w-5" />
                    </button>
                  )}
                  <button onClick={() => setOpenId(task.id)} className="min-w-0 flex-1 text-left">
                    <p className={cn("truncate text-sm font-medium", task.status === "completed" && "text-muted-foreground line-through")}>
                      {task.title}
                    </p>
                    <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                      <StatusPill tone="neutral" size="sm">{humanize(task.activity_type)}</StatusPill>
                      <StatusPill tone={PRIORITY_TONE[task.priority]} size="sm">{task.priority}</StatusPill>
                      {task.is_recurring && <Repeat className="h-3 w-3" />}
                      {task.source?.startsWith("automation") && <span>· auto</span>}
                    </div>
                  </button>
                  {task.due_at && (
                    <StatusPill tone={dueTone(task)} size="sm">
                      {new Date(task.due_at).toLocaleDateString()}
                    </StatusPill>
                  )}
                </Surface>
              ))}
            </div>
          ))}
        </div>
      )}

      {openId && (
        <TaskDrawer taskId={openId} onClose={() => setOpenId(null)} onChanged={() => void load()} />
      )}
    </div>
  );
}
