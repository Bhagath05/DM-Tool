"use client";

import { api, type RecommendationStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUSES: { value: RecommendationStatus; label: string }[] = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "skipped", label: "Skipped" },
];

export function RecommendationTaskStatus({
  recommendationId,
  status,
  onUpdated,
}: {
  recommendationId: string;
  status?: RecommendationStatus | null;
  onUpdated?: (status: RecommendationStatus) => void;
}) {
  const current = status ?? "not_started";

  async function setStatus(next: RecommendationStatus) {
    if (next === current) return;
    await api.advisor.updateStatus(recommendationId, next);
    onUpdated?.(next);
  }

  return (
    <div
      className="flex flex-wrap gap-1.5"
      data-testid="recommendation-task-status"
    >
      {STATUSES.map((s) => {
        const active = s.value === current;
        return (
          <button
            key={s.value}
            type="button"
            onClick={() => void setStatus(s.value)}
            className={cn(
              "rounded-md border px-2 py-0.5 text-[11px] transition-colors",
              active
                ? "border-foreground bg-foreground text-background"
                : "border-border text-muted-foreground hover:bg-muted",
            )}
          >
            {s.value === "completed" ? "✓ " : s.value === "skipped" ? "− " : ""}
            {s.label}
          </button>
        );
      })}
    </div>
  );
}
