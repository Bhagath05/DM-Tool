"use client";

import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { StatusPill } from "@/components/ui/status-pill";
import { api, ApiError, type AdvisorHistoryItem } from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; items: AdvisorHistoryItem[] };

export function HistoryPage() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const items = await api.advisor.history();
      setState({ kind: "ready", items });
    } catch (e) {
      setState({
        kind: "error",
        message:
          e instanceof ApiError
            ? e.message
            : "Couldn't load recommendation history.",
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading history…
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-destructive">
          {state.message}
        </CardContent>
      </Card>
    );
  }

  if (state.items.length === 0) {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-muted-foreground">
          No recommendations recorded yet. Visit Opportunities or Today&apos;s Plan
          to get your first advisor actions.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {state.items.map((item) => (
        <Card key={item.id}>
          <CardContent className="space-y-2 py-5">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{item.date}</span>
              <StatusPill>{item.status.replace("_", " ")}</StatusPill>
              <StatusPill>{`${item.impact_label} impact`}</StatusPill>
            </div>
            <h2 className="text-base font-semibold">{item.title}</h2>
            {item.observation && (
              <p className="text-sm">
                <span className="font-medium">Observation:</span> {item.observation}
              </p>
            )}
            {item.root_cause && (
              <p className="text-sm text-muted-foreground">
                <span className="font-medium">Root cause:</span> {item.root_cause}
              </p>
            )}
            {item.recommended_action && (
              <p className="text-sm">
                <span className="font-medium">Action:</span> {item.recommended_action}
              </p>
            )}
            <p className="text-sm text-muted-foreground">{item.description}</p>
            {item.result_summary && (
              <p className="text-sm">
                <span className="font-medium">Outcome:</span> {item.result_summary}
              </p>
            )}
            {item.learning && (
              <p className="text-sm">
                <span className="font-medium">Learning:</span> {item.learning}
              </p>
            )}
            {item.data_used && item.data_used.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Sources: {item.data_used.map((d) => `${d.label}: ${d.value}`).join(" · ")}
              </p>
            )}
            {item.expected_result && (
              <p className="text-sm text-muted-foreground">
                Expected: {item.expected_result}
              </p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
