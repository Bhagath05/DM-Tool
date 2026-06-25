"use client";

import { Flame, Snowflake, Star, Thermometer } from "lucide-react";

import type {
  AssetType,
  Lead,
  LeadPriorityBucket,
  LeadPriorityItem,
  LeadStatus,
} from "@/lib/api";
import { ASSET_TYPE_LABEL, humanizeSource } from "@/lib/humanize";
import { cn } from "@/lib/utils";

const STATUS_COLOR: Record<LeadStatus, string> = {
  new: "bg-blue-500/15 text-blue-700 dark:text-blue-300",
  hot: "bg-red-500/15 text-red-700 dark:text-red-300",
  warm: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  cold: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
  archived: "bg-muted text-muted-foreground",
};

// Phase 5 — priority badge palette + icons, mirrors intelligence-card's
// BUCKET_META so the inbox row and the priority list speak the same
// visual language.
const PRIORITY_META: Record<
  LeadPriorityBucket,
  { label: string; icon: typeof Flame; cls: string }
> = {
  focus: {
    label: "Focus",
    icon: Star,
    cls: "bg-primary/15 text-primary",
  },
  hot: {
    label: "Hot",
    icon: Flame,
    cls: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
  },
  warm: {
    label: "Warm",
    icon: Thermometer,
    cls: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  },
  cold: {
    label: "Cold",
    icon: Snowflake,
    cls: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
  },
};

export function LeadRow({
  lead,
  onSelect,
  priority,
}: {
  lead: Lead;
  onSelect: (l: Lead) => void;
  /** AI-ranked priority for this lead, or null if not in the top picks. */
  priority?: LeadPriorityItem | null;
}) {
  const priorityMeta = priority ? PRIORITY_META[priority.priority] : null;
  const PriorityIcon = priorityMeta?.icon;
  return (
    <button
      type="button"
      onClick={() => onSelect(lead)}
      data-testid={`lead-row${priority ? `-${priority.priority}` : ""}`}
      className={cn(
        "grid w-full grid-cols-[1fr_140px_120px_100px] items-center gap-3 px-4 py-3 text-left text-sm hover:bg-accent",
        // Highlight the AI's focus pick so the eye lands on it first.
        priority?.priority === "focus" && "bg-primary/5",
      )}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {priorityMeta && PriorityIcon && (
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                priorityMeta.cls,
              )}
              title={`AI rank #${priority!.rank} · ${priorityMeta.label}`}
            >
              <PriorityIcon className="h-3 w-3" />
              #{priority!.rank}
            </span>
          )}
          <span className="truncate font-medium">{lead.email}</span>
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
              STATUS_COLOR[lead.status],
            )}
          >
            {lead.status}
          </span>
        </div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground">
          {lead.name ?? "—"}
          {lead.company ? ` · ${lead.company}` : ""}
        </div>
        {priority && (
          <div
            className="mt-1 truncate text-xs text-primary/80"
            data-testid="lead-row-why-now"
            title={priority.why_now}
          >
            <span className="font-medium">Why now: </span>
            {priority.why_now}
          </div>
        )}
      </div>
      <div className="truncate text-xs text-muted-foreground">
        {lead.utm_campaign ??
          (lead.source_asset_type
            ? ASSET_TYPE_LABEL[lead.source_asset_type as AssetType] ??
              lead.source_asset_type
            : lead.landing_page_id
              ? "Lead page"
              : "Direct")}
      </div>
      <div className="truncate text-xs text-muted-foreground">
        {humanizeSource(lead.utm_source) ?? "—"}
      </div>
      <div className="text-right text-xs text-muted-foreground tabular-nums">
        {formatRelative(lead.created_at)}
      </div>
    </button>
  );
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return new Date(iso).toLocaleDateString();
}
