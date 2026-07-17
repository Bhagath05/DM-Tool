"use client";

/**
 * Work queue sections — the AI's queued work, grouped by what the owner
 * needs to do about it.
 *
 * Every item is a real `WorkItem` from GET /operations/work. Approve/dismiss
 * goes through the existing PATCH /operations/work/{id} — nothing new is
 * decided or calculated here. `rationale` is the AI's own plain-language
 * "why I queued this", so we surface it verbatim rather than inventing copy.
 */

import { Check, Clock, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { api, type WorkItem } from "@/lib/api";
import { cn } from "@/lib/utils";

const PRIORITY_TONE: Record<string, string> = {
  high: "bg-bad",
  medium: "bg-watch",
  low: "bg-muted-foreground/40",
};

export function WorkCard({
  item,
  onChanged,
}: {
  item: WorkItem;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<"approved" | "dismissed" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const act = async (status: "approved" | "dismissed") => {
    setBusy(status);
    setError(null);
    try {
      await api.operations.updateWork(item.id, status);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't work. Try again.");
      setBusy(null);
    }
  };

  const decided = item.status === "approved" || item.status === "dismissed";

  return (
    <li
      className="rounded-xl border border-border bg-background p-3.5"
      data-testid="work-item"
    >
      <div className="flex items-start gap-2.5">
        <span
          className={cn(
            "mt-1.5 h-2 w-2 shrink-0 rounded-full",
            PRIORITY_TONE[item.priority] ?? "bg-muted-foreground/40",
          )}
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{item.title}</p>
          {item.description && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {item.description}
            </p>
          )}

          {/* The AI's own reasoning — surfaced, never paraphrased. */}
          {item.rationale && (
            <p className="mt-2 rounded-md bg-ai-soft px-2.5 py-1.5 text-xs text-ai-soft-foreground">
              <span className="font-medium">Why I suggested this: </span>
              {item.rationale}
            </p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            {item.scheduled_for && (
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {new Date(item.scheduled_for).toLocaleString()}
              </span>
            )}
            {item.requires_approval && !decided && (
              <span className="rounded-full bg-watch-soft px-1.5 py-0.5 text-watch-soft-foreground">
                Needs your OK
              </span>
            )}
            {decided && (
              <span className="rounded-full bg-muted px-1.5 py-0.5">
                {item.status === "approved" ? "Approved" : "Dismissed"}
              </span>
            )}
          </div>

          {error && (
            <p className="mt-2 text-xs text-bad-soft-foreground">{error}</p>
          )}

          {!decided && (
            <div className="mt-2.5 flex gap-2">
              <Button
                size="sm"
                onClick={() => act("approved")}
                disabled={busy !== null}
              >
                <Check className="mr-1.5 h-3.5 w-3.5" />
                {busy === "approved" ? "Saving…" : "Yes, do it"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => act("dismissed")}
                disabled={busy !== null}
              >
                <X className="mr-1.5 h-3.5 w-3.5" />
                Not now
              </Button>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}
