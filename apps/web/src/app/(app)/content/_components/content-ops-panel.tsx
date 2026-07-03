"use client";

/**
 * Phase 6.2B — Enterprise Content Operations panel.
 *
 * A per-asset workspace over the EXISTING content-ops API (versions / review /
 * comments / folders / edit — no fabricated data). Four tabs:
 *   Edit     — field-level editor + debounced AUTOSAVE (with unsaved-draft
 *              recovery + last-saved timestamp + conflict detection).
 *   Versions — immutable history, restore, and two-version COMPARE with a
 *              word-level diff (add / delete / modify highlighted).
 *   Review   — approval workflow: current status, only the LEGAL next moves
 *              (mirrors the backend transition table), reason capture, history.
 *   Comments — threaded comments + @mentions + resolve / reopen.
 *
 * Everything is tenant-scoped + RBAC-gated + audited on the server; this panel
 * only orchestrates the calls. Design system reused throughout.
 */

import {
  Check,
  CornerDownRight,
  History,
  MessageSquare,
  Pencil,
  RotateCcw,
  Send,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { Surface } from "@/components/ui/surface";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  REVIEW_TRANSITIONS,
  type ContentComment,
  type ContentVersion,
  type GeneratedContent,
  type ReviewEvent,
  type ReviewStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = "edit" | "versions" | "review" | "comments";

const STATUS_TONE: Record<ReviewStatus, PillTone> = {
  draft: "neutral",
  in_review: "watch",
  changes_requested: "watch",
  approved: "good",
  rejected: "bad",
  published: "good",
  archived: "muted",
};

const SOURCE_TONE: Record<string, PillTone> = {
  ai: "ai",
  manual: "neutral",
  restore: "watch",
};

function humanize(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function timeAgo(iso: string): string {
  const d = new Date(iso);
  const s = Math.floor((Date.now() - d.getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return d.toLocaleDateString();
}

// ---- field editor: string + string[] top-level fields become editable ----
export type Field = { key: string; kind: "text" | "list"; value: string };

export function toFields(output: Record<string, unknown>): Field[] {
  const fields: Field[] = [];
  for (const [key, v] of Object.entries(output)) {
    if (typeof v === "string") fields.push({ key, kind: "text", value: v });
    else if (Array.isArray(v) && v.every((x) => typeof x === "string"))
      fields.push({ key, kind: "list", value: (v as string[]).join("\n") });
  }
  return fields;
}

// Reassemble the output preserving every non-editable field untouched.
export function fromFields(
  output: Record<string, unknown>,
  fields: Field[],
): Record<string, unknown> {
  const next = { ...output };
  for (const f of fields) {
    next[f.key] =
      f.kind === "list"
        ? f.value.split("\n").map((l) => l.trim()).filter(Boolean)
        : f.value;
  }
  return next;
}

const draftKey = (id: string) => `aicmo.content.draft.v1.${id}`;

// ---- word-level diff for version compare ----
function flatten(v: unknown, out: string[] = []): string[] {
  if (typeof v === "string") out.push(v);
  else if (Array.isArray(v)) v.forEach((x) => flatten(x, out));
  else if (v && typeof v === "object")
    Object.values(v as Record<string, unknown>).forEach((x) => flatten(x, out));
  return out;
}

export type DiffTok = { t: string; op: "same" | "add" | "del" };

export function wordDiff(a: string, b: string): DiffTok[] {
  const x = a.split(/(\s+)/);
  const y = b.split(/(\s+)/);
  const n = x.length;
  const m = y.length;
  // LCS table
  const lcs: number[][] = Array.from({ length: n + 1 }, () =>
    new Array<number>(m + 1).fill(0),
  );
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      lcs[i][j] =
        x[i] === y[j]
          ? lcs[i + 1][j + 1] + 1
          : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const out: DiffTok[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) {
      out.push({ t: x[i], op: "same" });
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      out.push({ t: x[i], op: "del" });
      i++;
    } else {
      out.push({ t: y[j], op: "add" });
      j++;
    }
  }
  while (i < n) out.push({ t: x[i++], op: "del" });
  while (j < m) out.push({ t: y[j++], op: "add" });
  return out;
}

export function ContentOpsPanel({
  content,
  open,
  onOpenChange,
  onChanged,
}: {
  content: GeneratedContent;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onChanged: (updated: GeneratedContent) => void;
}) {
  const [tab, setTab] = useState<Tab>("edit");

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={humanize(content.content_type)}
      description={content.goal}
      className="max-w-3xl"
      data-testid="content-ops-panel"
    >
      <div className="flex flex-col">
        {/* Tab bar */}
        <div className="flex gap-1 border-b border-border px-4 pt-2">
          {(
            [
              ["edit", "Edit", Pencil],
              ["versions", "History", History],
              ["review", "Review", Check],
              ["comments", "Comments", MessageSquare],
            ] as [Tab, string, typeof Pencil][]
          ).map(([id, lbl, Icon]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              data-testid={`ops-tab-${id}`}
              className={cn(
                "flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                tab === id
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {lbl}
            </button>
          ))}
          <StatusPill tone={STATUS_TONE[content.review_status]} size="sm" className="ml-auto self-center">
            {humanize(content.review_status)}
          </StatusPill>
        </div>

        <div className="p-4">
          {tab === "edit" && <EditTab content={content} onChanged={onChanged} />}
          {tab === "versions" && <VersionsTab content={content} onChanged={onChanged} />}
          {tab === "review" && <ReviewTab content={content} onChanged={onChanged} />}
          {tab === "comments" && <CommentsTab content={content} />}
        </div>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------- Edit tab
function EditTab({
  content,
  onChanged,
}: {
  content: GeneratedContent;
  onChanged: (u: GeneratedContent) => void;
}) {
  const [fields, setFields] = useState<Field[]>(() => toFields(content.output));
  const [summary, setSummary] = useState("");
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [conflict, setConflict] = useState(false);
  const [recoverable, setRecoverable] = useState<Field[] | null>(null);
  const baseUpdatedAt = useRef(content.updated_at);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dirty = useRef(false);

  // Recover an unsaved draft from a prior session.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(draftKey(content.id));
      if (!raw) return;
      const draft = JSON.parse(raw) as { fields: Field[]; base: string };
      const current = JSON.stringify(toFields(content.output));
      if (JSON.stringify(draft.fields) !== current) setRecoverable(draft.fields);
    } catch {
      /* ignore malformed draft */
    }
  }, [content.id, content.output]);

  const persistDraft = useCallback(
    (next: Field[]) => {
      try {
        localStorage.setItem(
          draftKey(content.id),
          JSON.stringify({ fields: next, base: baseUpdatedAt.current }),
        );
      } catch {
        /* storage may be full / unavailable */
      }
    },
    [content.id],
  );

  const save = useCallback(async () => {
    if (!dirty.current) return;
    setState("saving");
    try {
      // Conflict detection — did the server row move under us?
      const fresh = await api.content.byId(content.id);
      if (fresh.updated_at !== baseUpdatedAt.current) {
        setConflict(true);
        setState("error");
        return;
      }
      const output = fromFields(content.output, fields);
      const updated = await api.content.edit(
        content.id,
        output,
        summary.trim() || undefined,
      );
      baseUpdatedAt.current = updated.updated_at;
      dirty.current = false;
      setSavedAt(updated.updated_at);
      setState("saved");
      setSummary("");
      localStorage.removeItem(draftKey(content.id));
      onChanged(updated);
    } catch {
      setState("error");
    }
  }, [content.id, content.output, fields, summary, onChanged]);

  const onEdit = (idx: number, value: string) => {
    const next = fields.map((f, i) => (i === idx ? { ...f, value } : f));
    setFields(next);
    dirty.current = true;
    setState("idle");
    persistDraft(next);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => void save(), 1500); // autosave after idle
  };

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  if (fields.length === 0)
    return (
      <p className="text-sm text-muted-foreground">
        This asset has no editable text fields.
      </p>
    );

  return (
    <div className="space-y-3" data-testid="ops-edit">
      {recoverable && (
        <Surface state="watch" padding="compact" className="flex items-center justify-between gap-2 text-xs">
          <span>Unsaved changes from a previous session were found.</span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setFields(recoverable);
                dirty.current = true;
                setRecoverable(null);
              }}
            >
              Restore
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                localStorage.removeItem(draftKey(content.id));
                setRecoverable(null);
              }}
            >
              Discard
            </Button>
          </div>
        </Surface>
      )}
      {conflict && (
        <Surface state="bad" padding="compact" className="text-xs text-bad">
          This asset changed elsewhere since you opened it. Reload before saving
          to avoid overwriting newer edits.
        </Surface>
      )}

      {fields.map((f, i) => (
        <label key={f.key} className="block space-y-1">
          <span className="text-xs font-medium text-muted-foreground">
            {humanize(f.key)}
            {f.kind === "list" && " (one per line)"}
          </span>
          <Textarea
            value={f.value}
            onChange={(e) => onEdit(i, e.target.value)}
            rows={f.kind === "list" ? 4 : Math.min(8, Math.max(2, Math.ceil(f.value.length / 60)))}
            data-testid={`ops-field-${f.key}`}
          />
        </label>
      ))}

      <label className="block space-y-1">
        <span className="text-xs font-medium text-muted-foreground">
          Change summary (optional)
        </span>
        <Input
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          placeholder="What changed and why…"
          maxLength={280}
        />
      </label>

      <div className="flex items-center gap-3">
        <Button size="sm" onClick={() => void save()} disabled={state === "saving"}>
          Save now
        </Button>
        <span className="text-xs text-muted-foreground" data-testid="ops-save-status">
          {state === "saving" && "Saving…"}
          {state === "saved" && savedAt && `Saved ${timeAgo(savedAt)}`}
          {state === "error" && !conflict && "Save failed — retry."}
          {state === "idle" && dirty.current && "Autosaves after you pause…"}
        </span>
      </div>
    </div>
  );
}

// ------------------------------------------------------------ Versions tab
function VersionsTab({
  content,
  onChanged,
}: {
  content: GeneratedContent;
  onChanged: (u: GeneratedContent) => void;
}) {
  const [versions, setVersions] = useState<ContentVersion[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [pick, setPick] = useState<number[]>([]);
  const [diff, setDiff] = useState<DiffTok[] | null>(null);

  const load = useCallback(async () => {
    setVersions(await api.content.versions(content.id));
  }, [content.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const restore = async (version_no: number) => {
    if (!confirm(`Restore v${version_no}? This is captured as a new version.`)) return;
    setBusy(true);
    try {
      const updated = await api.content.restore(content.id, version_no);
      onChanged(updated);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const togglePick = (n: number) => {
    setDiff(null);
    setPick((p) =>
      p.includes(n) ? p.filter((x) => x !== n) : [...p, n].slice(-2),
    );
  };

  const compare = async () => {
    if (pick.length !== 2) return;
    const [a, b] = [...pick].sort((x, y) => x - y);
    const res = await api.content.compareVersions(content.id, a, b);
    setDiff(wordDiff(flatten(res.a.output).join(" "), flatten(res.b.output).join(" ")));
  };

  if (!versions)
    return <Skeleton className="h-32 w-full" />;

  if (versions.length === 0)
    return <p className="text-sm text-muted-foreground">No versions yet.</p>;

  return (
    <div className="space-y-3" data-testid="ops-versions">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>Select two versions to compare.</span>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto"
          disabled={pick.length !== 2}
          onClick={() => void compare()}
        >
          Compare {pick.length === 2 ? `v${Math.min(...pick)} ↔ v${Math.max(...pick)}` : ""}
        </Button>
      </div>

      {diff && (
        <Surface padding="compact" className="text-sm leading-relaxed" data-testid="ops-diff">
          {diff.map((d, i) => (
            <span
              key={i}
              className={cn(
                d.op === "add" && "rounded bg-good-soft text-good-soft-foreground",
                d.op === "del" && "rounded bg-bad-soft text-bad-soft-foreground line-through",
              )}
            >
              {d.t}
            </span>
          ))}
        </Surface>
      )}

      <ul className="space-y-2">
        {versions.map((v) => (
          <li key={v.id}>
            <Surface
              padding="compact"
              className={cn(
                "flex items-center gap-3",
                pick.includes(v.version_no) && "ring-1 ring-primary",
              )}
            >
              <input
                type="checkbox"
                checked={pick.includes(v.version_no)}
                onChange={() => togglePick(v.version_no)}
                className="h-4 w-4"
                aria-label={`Select v${v.version_no}`}
              />
              <span className="text-sm font-medium">v{v.version_no}</span>
              <StatusPill tone={SOURCE_TONE[v.edit_source] ?? "neutral"} size="sm">
                {v.edit_source === "ai" ? "AI" : humanize(v.edit_source)}
              </StatusPill>
              <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                {v.change_summary || "—"}
              </span>
              <span className="text-xs text-muted-foreground">{timeAgo(v.created_at)}</span>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => void restore(v.version_no)}
                title="Restore this version"
              >
                <RotateCcw className="h-4 w-4" />
              </Button>
            </Surface>
          </li>
        ))}
      </ul>
    </div>
  );
}

// -------------------------------------------------------------- Review tab
function ReviewTab({
  content,
  onChanged,
}: {
  content: GeneratedContent;
  onChanged: (u: GeneratedContent) => void;
}) {
  const [history, setHistory] = useState<ReviewEvent[] | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const status = content.review_status;
  const nextStates = REVIEW_TRANSITIONS[status] ?? [];

  const load = useCallback(async () => {
    setHistory(await api.content.reviewHistory(content.id));
  }, [content.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const move = async (to: ReviewStatus) => {
    setBusy(true);
    try {
      const updated = await api.content.review(content.id, to, reason.trim() || undefined);
      setReason("");
      onChanged(updated);
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="ops-review">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Current status</span>
        <StatusPill tone={STATUS_TONE[status]}>{humanize(status)}</StatusPill>
      </div>

      {nextStates.length > 0 ? (
        <div className="space-y-2">
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason (optional — recorded on the transition)"
            maxLength={1000}
          />
          <div className="flex flex-wrap gap-2">
            {nextStates.map((s) => (
              <Button
                key={s}
                size="sm"
                variant={s === "rejected" ? "destructive" : "outline"}
                disabled={busy}
                onClick={() => void move(s)}
                data-testid={`ops-review-to-${s}`}
              >
                {humanize(s)}
              </Button>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">No further transitions available.</p>
      )}

      <div className="space-y-2">
        <span className="text-xs font-medium text-muted-foreground">History</span>
        {!history ? (
          <Skeleton className="h-20 w-full" />
        ) : history.length === 0 ? (
          <p className="text-xs text-muted-foreground">No transitions yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {history.map((e) => (
              <li key={e.id} className="flex items-center gap-2 text-xs">
                <StatusPill tone={STATUS_TONE[e.from_status as ReviewStatus] ?? "neutral"} size="sm">
                  {humanize(e.from_status)}
                </StatusPill>
                <CornerDownRight className="h-3 w-3 text-muted-foreground" />
                <StatusPill tone={STATUS_TONE[e.to_status as ReviewStatus] ?? "neutral"} size="sm">
                  {humanize(e.to_status)}
                </StatusPill>
                {e.reason && <span className="truncate text-muted-foreground">— {e.reason}</span>}
                <span className="ml-auto text-muted-foreground">{timeAgo(e.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------ Comments tab
function CommentsTab({ content }: { content: GeneratedContent }) {
  const [comments, setComments] = useState<ContentComment[] | null>(null);
  const [body, setBody] = useState("");
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setComments(await api.content.comments(content.id));
  }, [content.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const parseMentions = (text: string): string[] =>
    Array.from(new Set((text.match(/@([\w.-]+)/g) ?? []).map((m) => m.slice(1))));

  const add = async () => {
    const text = body.trim();
    if (!text) return;
    setBusy(true);
    try {
      await api.content.addComment(content.id, text, {
        parent_id: replyTo ?? undefined,
        mentions: parseMentions(text),
      });
      setBody("");
      setReplyTo(null);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const toggleResolved = async (c: ContentComment) => {
    await api.content.resolveComment(c.id, !c.resolved);
    await load();
  };

  const { roots, childrenOf } = useMemo(() => {
    const list = comments ?? [];
    const childrenOf = new Map<string, ContentComment[]>();
    const roots: ContentComment[] = [];
    for (const c of list) {
      if (c.parent_id) {
        const arr = childrenOf.get(c.parent_id) ?? [];
        arr.push(c);
        childrenOf.set(c.parent_id, arr);
      } else roots.push(c);
    }
    return { roots, childrenOf };
  }, [comments]);

  const renderComment = (c: ContentComment, depth = 0) => (
    <div key={c.id} className={cn(depth > 0 && "ml-5 border-l border-border pl-3")}>
      <Surface padding="compact" className={cn("space-y-1", c.resolved && "opacity-60")}>
        <div className="flex items-center gap-2 text-xs">
          <span className="font-medium">{c.author_user_id}</span>
          <span className="text-muted-foreground">{timeAgo(c.created_at)}</span>
          {c.resolved && (
            <StatusPill tone="good" size="sm">
              Resolved
            </StatusPill>
          )}
          <div className="ml-auto flex gap-1">
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground"
              onClick={() => setReplyTo(c.id)}
            >
              Reply
            </button>
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground"
              onClick={() => void toggleResolved(c)}
            >
              {c.resolved ? "Reopen" : "Resolve"}
            </button>
          </div>
        </div>
        <p className="whitespace-pre-wrap text-sm">
          {c.body.split(/(@[\w.-]+)/).map((part, i) =>
            part.startsWith("@") ? (
              <span key={i} className="font-medium text-primary">
                {part}
              </span>
            ) : (
              part
            ),
          )}
        </p>
      </Surface>
      {(childrenOf.get(c.id) ?? []).map((child) => renderComment(child, depth + 1))}
    </div>
  );

  return (
    <div className="space-y-3" data-testid="ops-comments">
      <div className="space-y-2">
        {replyTo && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            Replying to a comment
            <button className="underline" onClick={() => setReplyTo(null)}>
              cancel
            </button>
          </div>
        )}
        <Textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Add a comment… use @name to mention"
          rows={2}
          data-testid="ops-comment-input"
        />
        <Button size="sm" onClick={() => void add()} disabled={busy || !body.trim()}>
          <Send className="h-4 w-4" />
          Comment
        </Button>
      </div>

      {!comments ? (
        <Skeleton className="h-20 w-full" />
      ) : roots.length === 0 ? (
        <p className="text-xs text-muted-foreground">No comments yet.</p>
      ) : (
        <div className="space-y-2">{roots.map((c) => renderComment(c))}</div>
      )}
    </div>
  );
}
