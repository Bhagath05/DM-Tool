"use client";

/**
 * Human approval surface for agent-proposed CONSEQUENTIAL actions (Phase 4C).
 *
 * The AI only ever PROPOSES a consequential action (e.g. publishing a scheduled
 * post); nothing runs until a human here explicitly approves it, and executing
 * is a second, deliberate step. The browser never calls a publishing service
 * directly — every button hits the approval API, which drives the server-side
 * state machine + re-validated execution.
 *
 * The screen keeps two things visually distinct: "the AI proposed this" (a
 * pending request) vs "you are approving this" (a deliberate confirmation).
 */

import { AlertTriangle, CheckCircle2, Clock, ShieldCheck, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonLines } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { api, type ApprovalView } from "@/lib/api";

export const dynamic = "force-dynamic";

const STATUS_TONE: Record<string, PillTone> = {
  pending: "watch",
  approved: "ai",
  executed: "good",
  rejected: "bad",
  failed: "bad",
  expired: "muted",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Awaiting your decision",
  approved: "Approved — ready to run",
  executed: "Done",
  rejected: "Rejected",
  failed: "Failed",
  expired: "Expired",
};

const TOOL_LABEL: Record<string, string> = {
  publish_scheduled_post: "Publish a scheduled post",
};

type ConfirmKind = "approve" | "reject" | "execute";

interface Confirm {
  kind: ConfirmKind;
  approval: ApprovalView;
}

function toolLabel(a: ApprovalView): string {
  return TOOL_LABEL[a.tool_name] ?? a.tool_name;
}

function when(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function argEntries(args: Record<string, unknown>): [string, string][] {
  return Object.entries(args).map(([k, v]) => [
    k.replace(/_/g, " "),
    typeof v === "string" ? v : JSON.stringify(v),
  ]);
}

export default function ApprovalsPage() {
  const [items, setItems] = useState<ApprovalView[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    return api.agentActions
      .list()
      .then((res) => {
        setItems(res.items);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const runAction = useCallback(async () => {
    if (!confirm) return;
    const { kind, approval } = confirm;
    setBusyId(approval.id);
    setActionError(null);
    try {
      if (kind === "approve") await api.agentActions.approve(approval.id);
      else if (kind === "reject") await api.agentActions.reject(approval.id, rejectReason || undefined);
      else await api.agentActions.execute(approval.id);
      setConfirm(null);
      setRejectReason("");
      await load();
    } catch (e) {
      setActionError(
        e instanceof Error ? e.message : "That action could not be completed. Nothing was changed.",
      );
    } finally {
      setBusyId(null);
    }
  }, [confirm, rejectReason, load]);

  const pending = (items ?? []).filter((a) => a.status === "pending");
  const approved = (items ?? []).filter((a) => a.status === "approved");
  const decisions = (items ?? []).filter(
    (a) => a.status !== "pending" && a.status !== "approved",
  );

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6" data-testid="approvals">
      <SectionHeading
        eyebrow="Human approval"
        heading="Actions waiting for your approval"
        description="Your AI marketer prepares consequential actions — like publishing a post — but never runs them on its own. You decide. Nothing goes out until you approve it here."
        size="lg"
      />
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-good" />
        You are the authorization. The AI cannot approve or execute these — only you can.
      </p>

      {loading && (
        <div className="flex flex-col gap-4" data-testid="approvals-loading">
          <SkeletonLines lines={3} />
          <SkeletonLines lines={3} />
        </div>
      )}

      {!loading && error && (
        <EmptyState
          icon={AlertTriangle}
          title="Couldn't load your approvals"
          description="Give it a moment and refresh — nothing has been approved or changed."
        />
      )}

      {!loading && !error && items && pending.length === 0 && approved.length === 0 && (
        <EmptyState
          icon={CheckCircle2}
          title="Nothing needs your approval"
          description="When your AI marketer prepares an action that needs sign-off, it'll appear here for you to review."
        />
      )}

      {/* Pending + approved-but-not-executed need action. */}
      {!loading && !error && (pending.length > 0 || approved.length > 0) && (
        <section className="flex flex-col gap-4" data-testid="approvals-pending">
          <h2 className="text-sm font-semibold">Needs your decision</h2>
          {[...pending, ...approved].map((a) => (
            <ApprovalCard
              key={a.id}
              approval={a}
              busy={busyId === a.id}
              onApprove={() => setConfirm({ kind: "approve", approval: a })}
              onReject={() => {
                setRejectReason("");
                setConfirm({ kind: "reject", approval: a });
              }}
              onExecute={() => setConfirm({ kind: "execute", approval: a })}
            />
          ))}
        </section>
      )}

      {/* Recent decisions (read-only history). */}
      {!loading && !error && decisions.length > 0 && (
        <section className="flex flex-col gap-3 border-t border-border pt-5" data-testid="approvals-decisions">
          <h2 className="text-sm font-semibold text-muted-foreground">Recent decisions</h2>
          {decisions.map((a) => (
            <div
              key={a.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border px-4 py-3"
              data-testid="approval-decision"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{toolLabel(a)}</p>
                <p className="text-xs text-muted-foreground">
                  {STATUS_LABEL[a.status] ?? a.status} · {when(a.decided_at ?? a.executed_at ?? a.updated_at)}
                </p>
              </div>
              <StatusPill tone={STATUS_TONE[a.status] ?? "neutral"}>{a.status}</StatusPill>
            </div>
          ))}
        </section>
      )}

      <ConfirmModal
        confirm={confirm}
        busy={busyId !== null}
        error={actionError}
        rejectReason={rejectReason}
        onRejectReasonChange={setRejectReason}
        onCancel={() => {
          setConfirm(null);
          setActionError(null);
        }}
        onConfirm={runAction}
      />
    </div>
  );
}

function ApprovalCard({
  approval,
  busy,
  onApprove,
  onReject,
  onExecute,
}: {
  approval: ApprovalView;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
  onExecute: () => void;
}) {
  const isApproved = approval.status === "approved";
  return (
    <div className="rounded-xl border border-border bg-card p-4" data-testid="approval-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ai">
            Proposed by your AI marketer
          </span>
          <p className="mt-0.5 text-sm font-semibold">{toolLabel(approval)}</p>
        </div>
        <StatusPill tone={STATUS_TONE[approval.status] ?? "neutral"}>
          {STATUS_LABEL[approval.status] ?? approval.status}
        </StatusPill>
      </div>

      {approval.reason && (
        <p className="mt-2 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Why:</span> {approval.reason}
        </p>
      )}
      {approval.expected_effect && (
        <p className="mt-1 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Expected effect:</span>{" "}
          {approval.expected_effect}
        </p>
      )}

      {argEntries(approval.arguments).length > 0 && (
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-lg bg-muted/40 p-3 text-xs" data-testid="approval-arguments">
          {argEntries(approval.arguments).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="font-medium text-muted-foreground">{k}</dt>
              <dd className="truncate font-mono text-foreground">{v}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="mt-3 flex items-center justify-between gap-3">
        <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
          <Clock className="h-3 w-3" />
          {isApproved
            ? `Approved — ready to run`
            : `Expires ${when(approval.expires_at)}`}
        </p>
        <div className="flex items-center gap-2">
          {!isApproved && (
            <>
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={onReject}
                data-testid="approval-reject"
              >
                <XCircle className="h-4 w-4" />
                Reject
              </Button>
              <Button
                size="sm"
                disabled={busy}
                onClick={onApprove}
                data-testid="approval-approve"
              >
                <CheckCircle2 className="h-4 w-4" />
                Approve
              </Button>
            </>
          )}
          {isApproved && (
            <Button
              size="sm"
              disabled={busy}
              onClick={onExecute}
              data-testid="approval-execute"
            >
              Publish now
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function ConfirmModal({
  confirm,
  busy,
  error,
  rejectReason,
  onRejectReasonChange,
  onCancel,
  onConfirm,
}: {
  confirm: Confirm | null;
  busy: boolean;
  error: string | null;
  rejectReason: string;
  onRejectReasonChange: (v: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const open = confirm !== null;
  const kind = confirm?.kind;
  const approval = confirm?.approval;

  const title =
    kind === "approve"
      ? "You are approving this action"
      : kind === "reject"
        ? "Reject this action?"
        : "Run this action now?";

  const confirmLabel =
    kind === "approve" ? "Approve" : kind === "reject" ? "Reject" : "Publish now";

  return (
    <Modal open={open} onOpenChange={(o) => !o && onCancel()} title={title}>
      {approval && (
        <div className="flex flex-col gap-3" data-testid="approval-confirm">
          <p className="text-sm">
            {kind === "approve" && (
              <>
                You — not the AI — are approving{" "}
                <span className="font-semibold">{toolLabel(approval)}</span>. It will move to
                approved; you then run it with a second, explicit step.
              </>
            )}
            {kind === "reject" && (
              <>
                This will reject <span className="font-semibold">{toolLabel(approval)}</span>. The
                AI cannot run it.
              </>
            )}
            {kind === "execute" && (
              <>
                This will run <span className="font-semibold">{toolLabel(approval)}</span> now. This
                is a real, consequential action.
              </>
            )}
          </p>

          {argEntries(approval.arguments).length > 0 && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-lg bg-muted/40 p-3 text-xs">
              {argEntries(approval.arguments).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="font-medium text-muted-foreground">{k}</dt>
                  <dd className="truncate font-mono">{v}</dd>
                </div>
              ))}
            </dl>
          )}

          {kind === "reject" && (
            <textarea
              value={rejectReason}
              onChange={(e) => onRejectReasonChange(e.target.value)}
              placeholder="Reason (optional)"
              rows={2}
              data-testid="approval-reject-reason"
              className="w-full rounded-md border border-border bg-background p-2 text-sm"
            />
          )}

          {error && (
            <p className="text-sm text-bad" data-testid="approval-action-error">
              {error}
            </p>
          )}

          <div className="mt-1 flex justify-end gap-2">
            <Button variant="outline" size="sm" disabled={busy} onClick={onCancel}>
              Cancel
            </Button>
            <Button
              variant={kind === "reject" ? "destructive" : "default"}
              size="sm"
              disabled={busy}
              onClick={onConfirm}
              data-testid="approval-confirm-button"
            >
              {busy ? "Working…" : confirmLabel}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
