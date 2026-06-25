"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { StatusDistribution } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUSES: {
  key: keyof StatusDistribution;
  label: string;
  className: string;
}[] = [
  { key: "new", label: "New", className: "bg-blue-500" },
  { key: "hot", label: "Hot", className: "bg-red-500" },
  { key: "warm", label: "Warm", className: "bg-amber-500" },
  { key: "cold", label: "Cold", className: "bg-slate-500" },
  { key: "archived", label: "Archived", className: "bg-muted-foreground/30" },
];

/** Inbox triage state — a horizontal stacked bar, simpler than a donut
 *  and reads better on small widths. */
export function StatusDonut({ status }: { status: StatusDistribution }) {
  const total = STATUSES.reduce((sum, s) => sum + status[s.key], 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Inbox triage</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {total === 0 ? (
          <p className="text-sm text-muted-foreground">
            No leads yet to triage.
          </p>
        ) : (
          <>
            <div className="flex h-3 overflow-hidden rounded-full bg-muted">
              {STATUSES.map((s) => {
                const v = status[s.key];
                if (v === 0) return null;
                const pct = (v / total) * 100;
                return (
                  <div
                    key={s.key}
                    className={cn("h-full", s.className)}
                    style={{ width: `${pct}%` }}
                    title={`${s.label}: ${v}`}
                  />
                );
              })}
            </div>
            <ul className="space-y-1.5 text-sm">
              {STATUSES.map((s) => (
                <li key={s.key} className="flex items-center gap-2">
                  <span
                    className={cn("h-2 w-2 shrink-0 rounded-full", s.className)}
                  />
                  <span className="flex-1">{s.label}</span>
                  <span className="font-mono tabular-nums text-muted-foreground">
                    {status[s.key]}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
