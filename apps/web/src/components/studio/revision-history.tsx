/**
 * RevisionHistory (CS1) — read-only timeline of a design's revisions.
 *
 * Every change (AI or human) is an immutable revision (Law 3). This panel
 * makes that visible: who/what/when, with the actor + mode. CS5 makes the
 * entries clickable for undo / branch / approve.
 */

"use client";

import type { RevisionSummary } from "@/lib/studio-types";

const SOURCE_LABEL: Record<string, string> = {
  ai_generate: "AI created",
  ai_edit: "AI edit",
  ai_regenerate: "AI regenerate",
  ai_restyle: "AI restyle",
  ai_transform: "AI transform",
  user_edit: "Manual edit",
  template: "From template",
};

function actorBadge(rev: RevisionSummary) {
  const isAi = rev.actor_kind === "ai";
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide"
      style={{
        background: isAi ? "rgba(37,99,235,0.12)" : "rgba(16,185,129,0.12)",
        color: isAi ? "#1d4ed8" : "#047857",
      }}
    >
      {rev.mode}
    </span>
  );
}

export function RevisionHistory({
  revisions,
  currentRevision,
}: {
  revisions: RevisionSummary[];
  currentRevision?: number;
}) {
  if (revisions.length === 0) {
    return <p className="text-sm text-[var(--muted-foreground,#64748b)]">No revisions yet.</p>;
  }
  const ordered = [...revisions].sort((a, b) => b.revision_n - a.revision_n);

  return (
    <ol className="space-y-2">
      {ordered.map((rev) => {
        const isHead = rev.revision_n === currentRevision;
        return (
          <li
            key={rev.id}
            className="flex items-start gap-3 rounded-md border p-2.5 text-sm"
            style={{
              borderColor: isHead ? "#2563eb" : "var(--border,#e2e8f0)",
              background: isHead ? "rgba(37,99,235,0.04)" : "transparent",
            }}
          >
            <span className="mt-0.5 font-mono text-xs text-[var(--muted-foreground,#64748b)]">
              v{rev.revision_n}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{SOURCE_LABEL[rev.source] ?? rev.source}</span>
                {actorBadge(rev)}
                {isHead && (
                  <span className="text-[10px] font-semibold uppercase text-[#2563eb]">current</span>
                )}
              </div>
              {rev.edit_summary && (
                <p className="truncate text-[var(--muted-foreground,#64748b)]">{rev.edit_summary}</p>
              )}
              <p className="text-[11px] text-[var(--muted-foreground,#94a3b8)]">
                {new Date(rev.created_at).toLocaleString()}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
