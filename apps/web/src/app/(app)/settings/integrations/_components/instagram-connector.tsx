"use client";

import { CheckCircle2, Loader2, RefreshCw, Unplug } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/ui/status-pill";
import { api, type SocialConnection } from "@/lib/api";
import { cn } from "@/lib/utils";

import { MarkInstagram } from "./platform-marks";

export function InstagramConnector() {
  const [connection, setConnection] = useState<SocialConnection | null>(null);
  const [available, setAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [avail, connections] = await Promise.all([
        api.social.availability(),
        api.social.connections(),
      ]);
      const igAvail = avail.find((a) => a.platform === "instagram");
      setAvailable(igAvail?.available ?? false);
      setConnection(connections.find((c) => c.platform === "instagram") ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load Instagram");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "instagram") {
      setStatus("Instagram connected — run Sync to pull posts and metrics.");
      void load();
    }
  }, [load]);

  const connected =
    connection?.source === "oauth" &&
    Boolean(connection.metadata_json?.ig_business_account_id);

  const handleConnect = async () => {
    setBusy(true);
    setError(null);
    try {
      const { authorize_url } = await api.social.oauthInit("instagram");
      window.location.href = authorize_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start OAuth");
      setBusy(false);
    }
  };

  const handleDisconnect = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.social.disconnect("instagram");
      setStatus("Instagram disconnected.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Disconnect failed");
    } finally {
      setBusy(false);
    }
  };

  const handleSync = async () => {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const result = await api.social.sync("instagram");
      setStatus(
        `Synced ${result.inserted_assets + result.updated_assets} posts.`,
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <article className="card-surface flex items-center gap-2 p-5 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading Instagram…
      </article>
    );
  }

  return (
    <article
      data-testid="integration-instagram"
      className={cn(
        "card-surface flex flex-col gap-4 p-5 sm:p-6",
        connected && "border-emerald-200/40 bg-emerald-50/20 dark:bg-emerald-950/10",
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border bg-card shadow-xs">
            {connected ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            ) : (
              <MarkInstagram />
            )}
          </span>
          <div className="flex flex-col gap-0.5">
            <h4 className="text-card-title font-semibold">Instagram</h4>
            <StatusPill
              tone={connected ? "good" : available ? "neutral" : "muted"}
              size="sm"
              dot
            >
              {connected ? "Connected" : available ? "Not connected" : "Coming soon"}
            </StatusPill>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {!connected && available && (
            <Button size="sm" onClick={handleConnect} disabled={busy}>
              Connect
            </Button>
          )}
          {connected && (
            <>
              <Button size="sm" variant="outline" onClick={handleSync} disabled={busy}>
                {busy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                Sync now
              </Button>
              <Button size="sm" variant="outline" onClick={handleConnect} disabled={busy}>
                Reconnect
              </Button>
              <Button size="sm" variant="ghost" onClick={handleDisconnect} disabled={busy}>
                <Unplug className="h-3.5 w-3.5" />
                Disconnect
              </Button>
            </>
          )}
        </div>
      </header>

      <p className="text-sm leading-relaxed text-muted-foreground">
        Connect your Instagram Business account to publish posts and sync reach,
        engagement, and content performance.
      </p>

      {connected && connection && (
        <dl className="grid gap-1 text-xs text-muted-foreground">
          {connection.metadata_json?.page_name != null && (
            <div>
              <dt className="inline font-medium text-foreground/80">Account: </dt>
              <dd className="inline">{String(connection.metadata_json.page_name)}</dd>
            </div>
          )}
          {connection.last_synced_at && (
            <div>
              <dt className="inline font-medium text-foreground/80">Last sync: </dt>
              <dd className="inline">
                {new Date(connection.last_synced_at).toLocaleString()}
              </dd>
            </div>
          )}
        </dl>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}
      {status && <p className="text-xs text-emerald-700">{status}</p>}

      {!available && (
        <p className="text-xs text-muted-foreground">
          OAuth credentials not configured — set IG_CLIENT_ID and IG_CLIENT_SECRET
          on the API server.
        </p>
      )}
    </article>
  );
}
