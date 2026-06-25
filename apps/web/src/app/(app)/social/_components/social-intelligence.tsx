"use client";

import {
  AlertCircle,
  Brain,
  CheckCircle2,
  Eye,
  Heart,
  Loader2,
  RefreshCw,
  Sparkles,
  Trophy,
  Users,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  api,
  type AudiencePattern,
  type SocialAsset,
  type SocialAvailability,
  type SocialConnection,
  type SocialPlatform,
  type WinningPattern,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * The Social Intelligence page. Three sections stacked top → bottom:
 *
 *  1. Connections — OAuth buttons (gated on dev-account config) + manual
 *     import textarea so the loop works today.
 *  2. Winning patterns — the LLM-derived signal the next generation
 *     inherits. The actual moat.
 *  3. Top performing posts + audience signals — supporting evidence.
 *
 * Deliberately NOT styled like Hootsuite / Buffer. No queue, no
 * scheduler, no calendar. This is intelligence software.
 */

type LoadState =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "missing" } // not onboarded yet
  | { kind: "error"; message: string };

export function SocialIntelligence() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [availability, setAvailability] = useState<SocialAvailability[]>([]);
  const [connections, setConnections] = useState<SocialConnection[]>([]);
  const [patterns, setPatterns] = useState<WinningPattern[]>([]);
  const [audience, setAudience] = useState<AudiencePattern[]>([]);
  const [assets, setAssets] = useState<SocialAsset[]>([]);

  const load = useCallback(async () => {
    try {
      const [av, cn, pa, au, ac] = await Promise.all([
        api.social.availability(),
        api.social.connections(),
        api.social.patterns(),
        api.social.audiencePatterns(),
        api.social.assets(undefined, 12),
      ]);
      setAvailability(av);
      setConnections(cn);
      setPatterns(pa);
      setAudience(au);
      setAssets(ac);
      setState({ kind: "ready" });
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setState({ kind: "missing" });
      } else {
        setState({
          kind: "error",
          message: e instanceof Error ? e.message : "Couldn't load social",
        });
      }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") {
    return <LoadingCard text="Reading the platforms…" />;
  }
  if (state.kind === "error") {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-destructive">
          {state.message}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <ConnectionsCard
        availability={availability}
        connections={connections}
        onChange={load}
      />
      <WinningPatternsCard patterns={patterns} onReanalyze={load} />
      <div className="grid gap-6 lg:grid-cols-2">
        <TopAssetsCard assets={assets} />
        <AudienceSignalsCard items={audience} />
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------
//  Connections + manual import
// ----------------------------------------------------------------------

function ConnectionsCard({
  availability,
  connections,
  onChange,
}: {
  availability: SocialAvailability[];
  connections: SocialConnection[];
  onChange: () => void | Promise<void>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Where the data comes from</CardTitle>
        <p className="text-xs text-muted-foreground">
          Connect a platform for live sync — or paste your own export below to
          test the intelligence loop today.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {availability.map((a) => {
            const c = connections.find((x) => x.platform === a.platform);
            return (
              <ConnectionRow
                key={a.platform}
                availability={a}
                connection={c}
                onChange={onChange}
              />
            );
          })}
        </div>
        <ManualImportBlock onImported={onChange} />
      </CardContent>
    </Card>
  );
}

function ConnectionRow({
  availability,
  connection,
  onChange,
}: {
  availability: SocialAvailability;
  connection: SocialConnection | undefined;
  onChange: () => void | Promise<void>;
}) {
  const isConnected = Boolean(connection);
  const isOAuthReady = availability.available;
  const canSync = isConnected && connection!.source === "oauth";
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  const handleConnect = async () => {
    try {
      const { authorize_url } = await api.social.oauthInit(
        availability.platform,
      );
      window.location.href = authorize_url;
    } catch (e) {
      alert(e instanceof Error ? e.message : "Couldn't start OAuth");
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncError(null);
    try {
      const result = await api.social.sync(availability.platform);
      await onChange();
      alert(
        `Synced ${result.inserted_assets} new + ${result.updated_assets} updated posts.`,
      );
    } catch (e) {
      setSyncError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-md border bg-card px-3 py-3",
        isConnected && "border-emerald-200/40 bg-emerald-50/30 dark:bg-emerald-950/20",
      )}
    >
      <div className="mt-0.5">
        {isConnected ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
        ) : (
          <PlatformIcon platform={availability.platform} />
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="text-sm font-medium capitalize">
          {availability.platform}
        </div>
        {isConnected ? (
          <p className="text-[11px] text-muted-foreground">
            Connected via{" "}
            {connection!.source === "oauth" ? "OAuth" : "manual import"}
            {connection!.last_synced_at &&
              ` · last sync ${new Date(connection!.last_synced_at).toLocaleDateString()}`}
          </p>
        ) : (
          <p className="text-[11px] text-muted-foreground">
            {availability.reason ?? "Ready to connect."}
          </p>
        )}
        {!isConnected && isOAuthReady && (
          <Button size="sm" variant="outline" onClick={handleConnect}>
            Connect
          </Button>
        )}
        {canSync && (
          <Button
            size="sm"
            variant="outline"
            onClick={handleSync}
            disabled={syncing}
          >
            {syncing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Sync now
          </Button>
        )}
        {syncError && (
          <p className="text-[11px] text-destructive">{syncError}</p>
        )}
      </div>
    </div>
  );
}

function PlatformIcon({ platform }: { platform: SocialPlatform }) {
  // Lightweight monogram badges keep this off the "social scheduler" look.
  const letter = platform[0].toUpperCase();
  return (
    <div className="flex h-4 w-4 items-center justify-center rounded-sm bg-muted text-[9px] font-semibold text-muted-foreground">
      {letter}
    </div>
  );
}

function ManualImportBlock({
  onImported,
}: {
  onImported: () => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [platform, setPlatform] = useState<SocialPlatform>("instagram");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const sample = JSON.stringify(
    {
      platform: "instagram",
      handle: "@yourbusiness",
      assets: [
        {
          platform_post_id: "demo_1",
          asset_type: "reel",
          caption: "Behind the bake — first batch of the day. #cafe #hyderabad",
          permalink: "https://instagram.com/p/demo_1",
          posted_at: "2026-05-20T08:00:00Z",
          hashtags: ["cafe", "hyderabad"],
          impressions: 1240,
          reach: 980,
          likes: 142,
          comments_count: 18,
          saves: 24,
          shares: 7,
          views: 1240,
        },
      ],
    },
    null,
    2,
  );

  const submit = async () => {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const parsed = JSON.parse(text);
      if (!parsed.platform) parsed.platform = platform;
      const result = await api.social.import(parsed);
      setStatus(
        `Imported ${result.inserted_assets} new + ${result.updated_assets} updated posts.`,
      );
      setText("");
      await onImported();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Couldn't parse — make sure it's valid JSON.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full rounded-md border border-dashed bg-muted/20 px-3 py-2.5 text-left text-xs text-muted-foreground hover:bg-muted/40"
      >
        Don&apos;t have OAuth set up yet? Paste exported data instead — same
        intelligence loop, zero setup.
      </button>
    );
  }

  return (
    <div className="space-y-3 rounded-md border bg-muted/20 p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">Manual import</div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Close
        </button>
      </div>
      <p className="text-xs text-muted-foreground">
        Paste a JSON array of posts + their metrics. We&apos;ll ingest them and
        you can run the analyzer right after.
      </p>
      <div className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">Platform:</span>
        {(["instagram", "facebook", "linkedin", "youtube", "tiktok"] as SocialPlatform[]).map(
          (p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPlatform(p)}
              className={cn(
                "rounded-full border px-2.5 py-0.5 capitalize",
                platform === p
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-input hover:bg-accent",
              )}
            >
              {p}
            </button>
          ),
        )}
      </div>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={`Paste JSON like:\n\n${sample}`}
        className="min-h-[200px] font-mono text-[11px]"
      />
      {error && <p className="text-xs text-destructive">{error}</p>}
      {status && <p className="text-xs text-emerald-700">{status}</p>}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          onClick={submit}
          disabled={busy || text.trim().length < 10}
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
          Import
        </Button>
        <button
          type="button"
          onClick={() => setText(sample)}
          className="text-[11px] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Load a sample
        </button>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------
//  Winning patterns — the moat
// ----------------------------------------------------------------------

function WinningPatternsCard({
  patterns,
  onReanalyze,
}: {
  patterns: WinningPattern[];
  onReanalyze: () => void | Promise<void>;
}) {
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const runAnalyzer = async () => {
    setAnalyzing(true);
    setResult(null);
    try {
      const r = await api.social.analyze();
      if (r.patterns_created === 0 && r.assets_considered < 3) {
        setResult(
          "Need at least 3 posts before we can extract patterns. Import a few more first.",
        );
      } else if (r.patterns_created === 0) {
        setResult(
          `Considered ${r.assets_considered} posts but couldn't extract high-confidence patterns yet. Add more data points and re-run.`,
        );
      } else {
        setResult(
          `${r.patterns_created} new pattern${r.patterns_created === 1 ? "" : "s"} extracted from ${r.assets_considered} posts.`,
        );
      }
      await onReanalyze();
    } catch (e) {
      setResult(
        e instanceof Error ? e.message : "Analyzer failed — try again.",
      );
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2 text-base">
            <Brain className="h-4 w-4 text-primary" />
            What&apos;s working — extracted from your posts
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Every generated reel, ad, and campaign inherits these patterns
            automatically. This is what makes the AI stop sounding generic.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={runAnalyzer}
          disabled={analyzing}
        >
          {analyzing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          Re-analyze
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {result && (
          <p className="rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            {result}
          </p>
        )}
        {patterns.length === 0 ? (
          <EmptyPatterns />
        ) : (
          <div className="space-y-2">
            {patterns.map((p) => (
              <PatternRow key={p.id} pattern={p} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PatternRow({ pattern }: { pattern: WinningPattern }) {
  const dims: { label: string; value: string | null }[] = [
    { label: "Hook", value: pattern.hook_pattern },
    { label: "Visual", value: pattern.visual_pattern },
    { label: "Caption", value: pattern.caption_pattern },
    { label: "CTA", value: pattern.cta_pattern },
    { label: "Format", value: pattern.format_pattern },
    { label: "Time", value: pattern.posting_time_pattern },
  ].filter((d): d is { label: string; value: string } => Boolean(d.value));

  return (
    <div className="space-y-2 rounded-md border bg-card px-4 py-3">
      <div className="flex items-start gap-2">
        <Trophy className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
        <div className="flex-1 text-sm font-medium leading-snug">
          {pattern.summary}
        </div>
        <div className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {Math.round(pattern.performance_score * 100)}% conf.
        </div>
      </div>
      {dims.length > 0 && (
        <dl className="ml-6 grid gap-x-3 gap-y-1 text-[11px] text-muted-foreground sm:grid-cols-2">
          {dims.map((d) => (
            <div key={d.label} className="flex gap-1">
              <dt className="font-medium text-foreground/70">{d.label}:</dt>
              <dd className="flex-1">{d.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function EmptyPatterns() {
  return (
    <div className="rounded-md border border-dashed bg-muted/20 px-4 py-6 text-center">
      <Sparkles className="mx-auto h-5 w-5 text-muted-foreground" />
      <p className="mt-2 text-sm font-medium">No patterns extracted yet</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Connect a platform (or paste at least 3 posts above) and hit{" "}
        <span className="font-medium">Re-analyze</span>. The AI reads your
        actual numbers and tells you what&apos;s working.
      </p>
    </div>
  );
}

// ----------------------------------------------------------------------
//  Top assets
// ----------------------------------------------------------------------

function TopAssetsCard({ assets }: { assets: SocialAsset[] }) {
  // Sort client-side by engagement rate for now; with more volume we'd
  // page this server-side.
  const ranked = [...assets].sort((a, b) => {
    const ra = a.latest_signal?.engagement_rate ?? 0;
    const rb = b.latest_signal?.engagement_rate ?? 0;
    return rb - ra;
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Zap className="h-4 w-4 text-amber-600" />
          Top performing posts
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Sorted by engagement rate. The AI uses the top of this list as
          examples when extracting patterns.
        </p>
      </CardHeader>
      <CardContent className="space-y-2">
        {ranked.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No posts synced yet.
          </p>
        ) : (
          ranked.slice(0, 6).map((a) => <AssetRow key={a.id} asset={a} />)
        )}
      </CardContent>
    </Card>
  );
}

function AssetRow({ asset }: { asset: SocialAsset }) {
  const s = asset.latest_signal;
  const eng = s ? `${(s.engagement_rate * 100).toFixed(1)}%` : "—";
  return (
    <a
      href={asset.permalink ?? "#"}
      target="_blank"
      rel="noreferrer"
      className="grid grid-cols-[1fr_auto] items-start gap-3 rounded-md border bg-card px-3 py-2 transition-colors hover:bg-accent/30"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          <span>{asset.platform}</span>
          <span>·</span>
          <span>{asset.asset_type}</span>
          {asset.posted_at && (
            <>
              <span>·</span>
              <span>{new Date(asset.posted_at).toLocaleDateString()}</span>
            </>
          )}
        </div>
        <p className="mt-0.5 line-clamp-2 text-xs">
          {asset.caption ?? "(no caption)"}
        </p>
        {s && (
          <div className="mt-1 flex items-center gap-3 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Heart className="h-3 w-3" />
              {s.likes}
            </span>
            <span className="inline-flex items-center gap-1">
              <Eye className="h-3 w-3" />
              {(s.reach || s.impressions || s.views).toLocaleString()}
            </span>
          </div>
        )}
      </div>
      <div className="text-right">
        <div className="text-sm font-semibold tabular-nums">{eng}</div>
        <div className="text-[9px] uppercase tracking-wide text-muted-foreground">
          engagement
        </div>
      </div>
    </a>
  );
}

// ----------------------------------------------------------------------
//  Audience signals
// ----------------------------------------------------------------------

function AudienceSignalsCard({ items }: { items: AudiencePattern[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Users className="h-4 w-4 text-primary" />
          Audience signals
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Patterns the AI noticed about who engages.
        </p>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <div className="rounded-md border border-dashed bg-muted/20 px-3 py-4 text-xs text-muted-foreground">
            No audience patterns yet — re-analyze once you&apos;ve imported
            enough posts.
          </div>
        ) : (
          <ul className="space-y-2">
            {items.map((a) => (
              <li
                key={a.id}
                className="rounded-md border bg-card px-3 py-2 text-xs"
              >
                <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  {a.pattern_type.replace(/_/g, " ")} ·{" "}
                  {Math.round(a.confidence_score * 100)}% conf.
                </div>
                <p className="mt-0.5">{a.description}</p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

// ----------------------------------------------------------------------
//  Loading helper
// ----------------------------------------------------------------------

function LoadingCard({ text }: { text: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {text}
      </CardContent>
    </Card>
  );
}

void AlertCircle;
