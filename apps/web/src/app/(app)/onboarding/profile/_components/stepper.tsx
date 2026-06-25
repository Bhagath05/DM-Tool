import { Check } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

export function Stepper({
  current,
  labels,
}: {
  current: number;
  labels: readonly string[];
}) {
  const percent = ((current + 1) / labels.length) * 100;
  return (
    <div className="space-y-3">
      <Progress value={percent} />
      <div className="flex justify-between text-[11px] uppercase tracking-wide">
        {labels.map((label, i) => {
          const done = i < current;
          const active = i === current;
          return (
            <div
              key={label}
              className={cn(
                "flex items-center gap-1",
                active
                  ? "font-semibold text-foreground"
                  : done
                    ? "text-foreground/80"
                    : "text-muted-foreground",
              )}
            >
              {done ? (
                <Check className="h-3 w-3" />
              ) : (
                <span className="inline-block w-3 text-center">{i + 1}</span>
              )}
              <span className="hidden sm:inline">{label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
