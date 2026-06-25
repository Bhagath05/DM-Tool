"use client";

import { CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/ui/status-pill";
import {
  ApiError,
  api,
  type IntegrationCatalogEntry,
  type IntegrationConnection,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const GBP_SLUG = "google_business_profile";

function oauthCallbackUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return `${base}/api/v1/integrations/oauth/callback`;
}

export function GoogleBusinessProfileConnector() {
  const [entry, setEntry] = useState<IntegrationCatalogEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await api.integrations.catalog();
      const gbp = items.find((i) => i.provider.slug === GBP_SLUG) ?? null;
      setEntry(gbp);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load integrations");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "1" && params.get("provider") === GBP_SLUG) {
      setStatus("Google Business Profile connected — run Sync to pull metrics.");
      void load();
    }
    if (params.get("error") === "oauth_failed") {
      setError("OAuth failed — try connecting again.");
    }
  }, [load]);

  const connection = entry?.connection ?? null;
  const provider = entry?.provider;
  const isActive = connection?.state === "ACTIVE";

  const handleConnect = async () => {
    if (!provider?.available) return;
    setBusy(true);
    setError(null);
    try {
      const { authorize_url } = await api.integrations.connect(
        GBP_SLUG,
        oauthCallbackUrl(),
      );
      window.location.href = authorize_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start OAuth");
      setBusy(false);
    }
  };

  const handleSync = async () => {
    if (!connection) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const result = await api.integrations.sync(connection.id);
      setStatus(
        result.rows_pulled > 0
          ? `Synced ${result.rows_pulled} metrics from Google.`
          : "Sync completed — no new metrics returned (check listing access).",
      );
      await load();
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) {
        setError("Google Business Profile OAuth isn't configured on this server.");
      } else {
        setError(e instanceof Error ? e.message : "Sync failed");
      }
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <article className="card-surface flex items-center gap-2 p-5 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading Google Business Profile…
      </article>
    );
  }

  return (
    <article
      data-testid="integration-google-business-profile"
      className={cn(
        "card-surface flex flex-col gap-4 p-5 sm:p-6",
        isActive && "border-emerald-200/40 bg-emerald-50/20 dark:bg-emerald-950/10",
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border bg-card shadow-xs">
            {isActive ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            ) : (
              <MarkGoogle />
            )}
          </span>
          <div className="flex flex-col gap-0.5">
            <h4 className="text-card-title font-semibold">
              Google Business Profile
            </h4>
            <StatusPill
              tone={isActive ? "good" : provider?.available ? "neutral" : "muted"}
              size="sm"
              dot
            >
              {connectionStateLabel(connection, provider?.available ?? false)}
            </StatusPill>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          {!isActive && provider?.available && (
            <Button size="sm" onClick={handleConnect} disabled={busy}>
              Connect
            </Button>
          )}
          {isActive && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleSync}
              disabled={busy}
            >
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              Sync now
            </Button>
          )}
        </div>
      </header>

      <p className="text-sm leading-relaxed text-muted-foreground">
        Pull reviews, phone calls, direction requests, website clicks, and
        profile views — direct business outcome signals for recommendations.
      </p>

      {isActive && connection && (
        <ConnectionMeta connection={connection} />
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}
      {status && <p className="text-xs text-emerald-700">{status}</p>}

      {!provider?.available && (
        <p className="text-xs text-muted-foreground">
          OAuth credentials not configured — set GOOGLE_GBP_CLIENT_ID and
          GOOGLE_GBP_CLIENT_SECRET on the API server.
        </p>
      )}
    </article>
  );
}

function connectionStateLabel(
  connection: IntegrationConnection | null,
  available: boolean,
): string {
  if (!connection || connection.state === "DISCONNECTED") {
    return available ? "Not connected" : "Coming soon";
  }
  if (connection.state === "ACTIVE") return "Connected";
  if (connection.state === "PENDING_AUTH") return "Connecting…";
  if (connection.state === "ERROR") return "Error — reconnect";
  return connection.state.toLowerCase().replace(/_/g, " ");
}

function ConnectionMeta({ connection }: { connection: IntegrationConnection }) {
  return (
    <dl className="grid gap-1 text-xs text-muted-foreground">
      {connection.external_account_name && (
        <div>
          <dt className="inline font-medium text-foreground/80">Location: </dt>
          <dd className="inline">{connection.external_account_name}</dd>
        </div>
      )}
      {connection.last_sync_at && (
        <div>
          <dt className="inline font-medium text-foreground/80">Last sync: </dt>
          <dd className="inline">
            {new Date(connection.last_sync_at).toLocaleString()}
          </dd>
        </div>
      )}
    </dl>
  );
}

function MarkGoogle() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="#EA4335" strokeWidth="2" />
      <path d="M12 3a9 9 0 0 1 9 9h-9z" fill="#FBBC05" />
      <path d="M21 12a9 9 0 0 1-9 9v-9z" fill="#34A853" />
      <path d="M12 21a9 9 0 0 1-9-9h9z" fill="#4285F4" />
    </svg>
  );
}
