"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { TimelineResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

/** CSS-bar timeline. No charting library — 30 bars in a flex row.
 *  Why not recharts/d3: this chart is read-only, monotone scale, no
 *  interaction beyond hover. A library would be ~80kb of payload for
 *  a feature we can ship in 40 lines of CSS. */
export function Timeline({
  data,
  windowDays,
  onWindowChange,
}: {
  data: TimelineResponse;
  windowDays: 7 | 14 | 30 | 90;
  onWindowChange: (w: 7 | 14 | 30 | 90) => void;
}) {
  const max = Math.max(1, ...data.days.map((d) => d.leads));

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
        <div>
          <CardTitle className="text-base">Leads over time</CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            {data.total.toLocaleString()} leads in the last {data.window_days} days
          </p>
        </div>
        <div className="flex gap-1">
          {([7, 14, 30, 90] as const).map((w) => (
            <button
              key={w}
              type="button"
              onClick={() => onWindowChange(w)}
              className={cn(
                "rounded px-2 py-0.5 text-[11px] transition-colors",
                windowDays === w
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              {w}d
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {data.total === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            No leads in this window. Publish a lead page and share the URL.
          </div>
        ) : (
          <>
            <div className="flex h-32 items-end gap-[2px]">
              {data.days.map((d) => {
                const pct = (d.leads / max) * 100;
                return (
                  <div
                    key={d.day}
                    className="group relative flex-1"
                    title={`${d.day}: ${d.leads} lead${d.leads === 1 ? "" : "s"}`}
                  >
                    <div
                      className={cn(
                        "w-full rounded-sm transition-colors",
                        d.leads > 0
                          ? "bg-primary group-hover:bg-primary/80"
                          : "bg-muted",
                      )}
                      style={{
                        height: `${Math.max(pct, d.leads > 0 ? 4 : 1)}%`,
                      }}
                    />
                  </div>
                );
              })}
            </div>
            <div className="mt-2 flex justify-between text-[10px] text-muted-foreground">
              <span>{data.days[0]?.day}</span>
              <span>{data.days[data.days.length - 1]?.day}</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
