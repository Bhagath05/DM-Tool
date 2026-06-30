"use client";

import {
  ArrowDown,
  CalendarDays,
  FileText,
  Globe,
  ImageIcon,
  Inbox,
  Megaphone,
  MousePointerClick,
  Plus,
  Sparkles,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type AssetType,
  type Lead,
  type LeadPriorityItem,
  type LeadStatus,
} from "@/lib/api";
import {
  ASSET_TYPE_PHRASE,
  describeClickPath,
  humanizeUtmContent,
} from "@/lib/humanize";
import { cn } from "@/lib/utils";

const STATUSES: { value: LeadStatus; label: string }[] = [
  { value: "new", label: "New" },
  { value: "hot", label: "Hot" },
  { value: "warm", label: "Warm" },
  { value: "cold", label: "Cold" },
  { value: "archived", label: "Archived" },
];

export function LeadDrawer({
  lead,
  onClose,
  onUpdated,
  onDeleted,
  priority,
}: {
  lead: Lead;
  onClose: () => void;
  onUpdated: (lead: Lead) => void;
  onDeleted: (id: string) => void;
  /** Phase 5 — AI priority for this lead if it made the top picks. */
  priority?: LeadPriorityItem | null;
}) {
  const [notes, setNotes] = useState(lead.notes ?? "");
  const [status, setStatus] = useState<LeadStatus>(lead.status);
  const [tags, setTags] = useState<string[]>(lead.tags ?? []);
  const [tagInput, setTagInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset local state when the user switches leads while drawer is open
  useEffect(() => {
    setNotes(lead.notes ?? "");
    setStatus(lead.status);
    setTags(lead.tags ?? []);
    setTagInput("");
    setError(null);
  }, [lead.id, lead.notes, lead.status, lead.tags]);

  const saveNotes = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.leads.update(lead.id, { notes });
      onUpdated(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const changeStatus = async (next: LeadStatus) => {
    const prev = status;
    setStatus(next); // optimistic
    try {
      const updated = await api.leads.update(lead.id, { status: next });
      onUpdated(updated);
    } catch (e) {
      setStatus(prev);
      setError(e instanceof Error ? e.message : "Could not update status");
    }
  };

  const persistTags = async (next: string[]) => {
    const prev = tags;
    setTags(next); // optimistic
    setError(null);
    try {
      const updated = await api.leads.update(lead.id, { tags: next });
      onUpdated(updated);
    } catch (e) {
      setTags(prev);
      setError(e instanceof Error ? e.message : "Could not update tags");
    }
  };

  const addTag = () => {
    const t = tagInput.trim().toLowerCase();
    if (!t) return;
    if (tags.includes(t)) {
      setTagInput("");
      return;
    }
    if (tags.length >= 20) {
      setError("Up to 20 tags per lead.");
      return;
    }
    setTagInput("");
    void persistTags([...tags, t]);
  };

  const removeTag = (t: string) => {
    void persistTags(tags.filter((x) => x !== t));
  };

  const remove = async () => {
    if (!confirm("Delete this lead? This cannot be undone.")) return;
    try {
      await api.leads.delete(lead.id);
      onDeleted(lead.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/40"
      onClick={onClose}
    >
      <aside
        className="h-full w-full max-w-md overflow-y-auto border-l border-border bg-card shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-card px-5 py-3">
          <div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Lead
            </div>
            <div className="text-sm font-semibold">{lead.email}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-6 p-5">
          {/* Phase 5 — AI opportunity block. Renders ONLY when this
              lead was ranked by the intelligence engine. Sits at the
              very top so the founder sees the action before any of the
              raw inbox plumbing. */}
          {priority && <OpportunityBlock priority={priority} />}

          {/* Status picker */}
          <section className="space-y-2">
            <Label>Status</Label>
            <div className="flex flex-wrap gap-1.5">
              {STATUSES.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => changeStatus(s.value)}
                  className={cn(
                    "rounded-md border px-2.5 py-1 text-xs",
                    status === s.value
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input hover:bg-accent",
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </section>

          {/* Lead identity */}
          <section className="space-y-2 text-sm">
            <Label>Identity</Label>
            <DetailGrid>
              <Detail label="Name">{lead.name ?? "—"}</Detail>
              <Detail label="Email">{lead.email}</Detail>
              <Detail label="Phone">{lead.phone ?? "—"}</Detail>
              <Detail label="Company">{lead.company ?? "—"}</Detail>
            </DetailGrid>
            {lead.message && (
              <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
                <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  Message
                </div>
                <p className="mt-1 whitespace-pre-wrap">{lead.message}</p>
              </div>
            )}
          </section>

          {/* "How they found you" — the path this lead took from asset to capture */}
          <section className="space-y-2 text-sm">
            <Label>How they found you</Label>
            <p className="text-xs text-muted-foreground">
              The journey this person took before joining your list.
            </p>
            <AttributionChain lead={lead} />
          </section>

          {/* Extra form data */}
          {Object.keys(lead.extra_data).length > 0 && (
            <section className="space-y-2 text-sm">
              <Label>Extra form data</Label>
              <DetailGrid>
                {Object.entries(lead.extra_data).map(([k, v]) => (
                  <Detail key={k} label={k}>
                    {String(v)}
                  </Detail>
                ))}
              </DetailGrid>
            </section>
          )}

          {/* Notes */}
          <section className="space-y-2">
            <Label htmlFor="lead-notes">Notes</Label>
            <Textarea
              id="lead-notes"
              rows={4}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Anything you want to remember about this lead…"
            />
            <Button size="sm" onClick={saveNotes} disabled={saving}>
              Save notes
            </Button>
          </section>

          {/* Tags — segment leads for filtering + follow-up */}
          <section className="space-y-2">
            <Label htmlFor="lead-tag-input">Tags</Label>
            <p className="text-xs text-muted-foreground">
              Group leads so you can filter and follow up by segment.
            </p>
            {tags.length > 0 ? (
              <div className="flex flex-wrap gap-1.5" data-testid="lead-tags">
                {tags.map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs"
                  >
                    <Tag className="h-3 w-3 text-muted-foreground" />
                    {t}
                    <button
                      type="button"
                      onClick={() => removeTag(t)}
                      aria-label={`Remove tag ${t}`}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <p
                className="text-xs text-muted-foreground/70"
                data-testid="lead-tags-empty"
              >
                No tags yet.
              </p>
            )}
            <div className="flex gap-2">
              <Input
                id="lead-tag-input"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addTag();
                  }
                }}
                placeholder="Add a tag (e.g. vip, follow-up)…"
                className="h-8 text-xs"
              />
              <Button
                size="sm"
                variant="outline"
                onClick={addTag}
                disabled={!tagInput.trim()}
              >
                <Plus className="h-3.5 w-3.5" />
                Add
              </Button>
            </div>
          </section>

          {error && <p className="text-sm text-destructive">{error}</p>}

          {/* Danger */}
          <section className="border-t border-border pt-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={remove}
              className="text-destructive"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete lead
            </Button>
          </section>

          <div className="text-[11px] text-muted-foreground">
            Captured {new Date(lead.created_at).toLocaleString()}
          </div>
        </div>
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Phase 5 — Opportunity block (AI priority for this lead)
// ---------------------------------------------------------------------
//
// Carries the FULL Constitution contract — what's happening, what to
// do, expected result, confidence, why. Same shape as
// `<AiRecommendation>` in spirit but compacted for the drawer (the
// inbox card above the list already renders the full advisor surface;
// the drawer block is the quick recap when a founder opens the lead).

const PRIORITY_TILE: Record<
  LeadPriorityItem["priority"],
  { label: string; cls: string }
> = {
  focus: {
    label: "Focus this lead",
    cls: "border-primary/30 bg-primary/5 text-primary",
  },
  hot: {
    label: "Hot",
    cls: "border-rose-500/30 bg-rose-500/5 text-rose-700 dark:text-rose-300",
  },
  warm: {
    label: "Warm",
    cls: "border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-300",
  },
  cold: {
    label: "Cold",
    cls: "border-slate-500/30 bg-slate-500/5 text-slate-700 dark:text-slate-300",
  },
};

const VALUE_BAND_LABEL: Record<LeadPriorityItem["estimated_value_band"], string> = {
  high: "High value",
  medium: "Medium value",
  low: "Small but worth it",
  unknown: "Value unclear",
};

function confidenceBand(confidence: number): { label: string; cls: string } {
  if (confidence >= 80)
    return {
      label: "High confidence",
      cls: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    };
  if (confidence >= 60)
    return {
      label: "Medium confidence",
      cls: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
    };
  if (confidence >= 40)
    return {
      label: "Low confidence",
      cls: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
    };
  return {
    label: "Speculative",
    cls: "bg-muted text-muted-foreground",
  };
}

function OpportunityBlock({ priority }: { priority: LeadPriorityItem }) {
  const tile = PRIORITY_TILE[priority.priority];
  const band = confidenceBand(priority.confidence);
  return (
    <section
      data-testid="lead-drawer-opportunity"
      className={cn("space-y-3 rounded-md border p-4", tile.cls)}
    >
      <header className="flex flex-wrap items-center gap-2 text-[10px] font-semibold uppercase tracking-wide">
        <Sparkles className="h-3.5 w-3.5" />
        AI opportunity
        <span className="rounded bg-background/60 px-1.5 py-0.5 text-foreground">
          {tile.label} · #{priority.rank}
        </span>
        <span className="rounded bg-background/60 px-1.5 py-0.5 text-foreground">
          {VALUE_BAND_LABEL[priority.estimated_value_band]}
        </span>
      </header>
      <div className="space-y-2 text-sm text-foreground">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Why now
          </div>
          <p className="mt-0.5 leading-snug">{priority.why_now}</p>
        </div>
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Do this
          </div>
          <p className="mt-0.5 font-medium leading-snug">
            {priority.recommended_action}
          </p>
        </div>
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            What to expect
          </div>
          <p className="mt-0.5 leading-snug text-muted-foreground">
            {priority.expected_result}
          </p>
        </div>
      </div>
      <footer className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
        <span
          className={cn(
            "inline-flex items-center rounded-md px-1.5 py-0.5 font-medium",
            band.cls,
          )}
        >
          {band.label} ({priority.confidence}%)
        </span>
        <span className="italic">{priority.reason}</span>
      </footer>
    </section>
  );
}

function DetailGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-x-3 gap-y-2 sm:grid-cols-2">{children}</div>;
}

function Detail({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="truncate text-sm">{children}</div>
    </div>
  );
}

/**
 * Visual chain showing the path from asset → click → landing page → capture.
 * Steps with no data are still rendered (greyed out) so the user can see what
 * was missing and fix it next time — without ever seeing "utm" or "id".
 */
function AttributionChain({ lead }: { lead: Lead }) {
  const assetType = lead.source_asset_type as AssetType | null;
  const assetIcon = assetType
    ? ASSET_ICON[assetType] ?? Sparkles
    : Sparkles;

  const assetSubtitle = assetType
    ? ASSET_TYPE_PHRASE[assetType] ?? "Something you generated"
    : "Came in without an attached asset";

  const slotLabel = humanizeUtmContent(lead.utm_content ?? null);
  const assetMeta = slotLabel ?? undefined;

  // "From Instagram · Paid social · Spring Launch"
  const clickSummary = describeClickPath({
    utm_source: lead.utm_source,
    utm_medium: lead.utm_medium,
    utm_campaign: lead.utm_campaign,
  });

  const referrerHost = (() => {
    if (!lead.referrer) return null;
    try {
      return new URL(lead.referrer).hostname;
    } catch {
      return lead.referrer;
    }
  })();

  return (
    <div className="space-y-0">
      <ChainStep
        icon={assetIcon}
        title="What they saw"
        subtitle={assetSubtitle}
        meta={assetMeta}
        muted={!assetType}
      />
      <ChainArrow />
      <ChainStep
        icon={MousePointerClick}
        title="How they got here"
        subtitle={
          clickSummary || referrerHost || "Came in directly — no tracking link used"
        }
        meta={
          referrerHost && clickSummary
            ? `Last site: ${referrerHost}`
            : undefined
        }
        muted={!clickSummary && !referrerHost}
      />
      <ChainArrow />
      <ChainStep
        icon={Globe}
        title="Where they landed"
        subtitle={
          lead.landing_page_id
            ? "Your lead page"
            : "Form posted directly — no landing page attached"
        }
        muted={!lead.landing_page_id}
      />
      <ChainArrow />
      <ChainStep
        icon={Inbox}
        title="Joined your list"
        subtitle={new Date(lead.created_at).toLocaleString()}
        accent
      />
    </div>
  );
}

const ASSET_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  content: FileText,
  ad: Megaphone,
  visual: ImageIcon,
  campaign: CalendarDays,
};

function ChainStep({
  icon: Icon,
  title,
  subtitle,
  meta,
  muted,
  accent,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  subtitle: string;
  meta?: string;
  muted?: boolean;
  accent?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-md border px-3 py-2",
        accent
          ? "border-primary/30 bg-primary/5"
          : muted
            ? "border-dashed border-border bg-muted/20"
            : "border-border bg-card",
      )}
    >
      <div
        className={cn(
          "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          accent
            ? "bg-primary text-primary-foreground"
            : muted
              ? "bg-muted text-muted-foreground"
              : "bg-foreground text-background",
        )}
      >
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="min-w-0 flex-1">
        <div
          className={cn(
            "text-[10px] font-medium uppercase tracking-wide",
            muted ? "text-muted-foreground/70" : "text-muted-foreground",
          )}
        >
          {title}
        </div>
        <div
          className={cn(
            "truncate text-sm",
            muted ? "text-muted-foreground" : "text-foreground",
          )}
        >
          {subtitle}
        </div>
        {meta && (
          <div className="truncate text-[11px] text-muted-foreground">
            {meta}
          </div>
        )}
      </div>
    </div>
  );
}

function ChainArrow() {
  return (
    <div className="flex justify-start pl-3">
      <ArrowDown className="my-1 h-3 w-3 text-muted-foreground" />
    </div>
  );
}
