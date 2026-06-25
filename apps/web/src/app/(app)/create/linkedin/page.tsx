"use client";

/**
 * LinkedIn Studio — topic in → a branded announcement poster + a ready-to-post
 * long-form caption. Generate, tweak the headline and re-render the image,
 * edit the caption, then copy + download to post on LinkedIn.
 *
 * The image is produced server-side (HTML/CSS → PNG), so the text is always
 * crisp and on-brand — not AI-garbled. Flag-gated by `poster_enabled`.
 */

import {
  Check,
  Copy,
  Download,
  Image as ImageIcon,
  Loader2,
  RefreshCw,
  Sparkles,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  ApiError,
  type LinkedInComposeResult,
  type LinkedInCopy,
} from "@/lib/api";

export const dynamic = "force-dynamic";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Caps = { enabled: boolean; renderer_available: boolean } | null;

export default function LinkedInStudioPage() {
  const [caps, setCaps] = useState<Caps>(null);
  const [capsLoading, setCapsLoading] = useState(true);

  const [topic, setTopic] = useState("");
  const [goal, setGoal] = useState("");
  const [genImage, setGenImage] = useState(true);

  const [busy, setBusy] = useState<null | "compose" | "render">(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LinkedInComposeResult | null>(null);
  const [body, setBody] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api.poster
      .capabilities()
      .then(setCaps)
      .catch(() => setCaps({ enabled: false, renderer_available: false }))
      .finally(() => setCapsLoading(false));
  }, []);

  const applyResult = useCallback((r: LinkedInComposeResult) => {
    setResult(r);
    setBody(r.post_body);
  }, []);

  async function generate() {
    if (topic.trim().length < 3) return;
    setBusy("compose");
    setError(null);
    try {
      const r = await api.poster.compose({
        topic: topic.trim(),
        goal: goal.trim() || null,
        generate_image: genImage,
      });
      applyResult(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't generate. Try again.");
    } finally {
      setBusy(null);
    }
  }

  async function rerender(fields: LinkedInCopy) {
    setBusy("render");
    setError(null);
    try {
      const r = await api.poster.render({ fields, generate_image: genImage });
      // keep the user's edited caption; only the image + fields change
      setResult({ ...r, post_body: body });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't re-render the image.");
    } finally {
      setBusy(null);
    }
  }

  function setField<K extends keyof LinkedInCopy>(key: K, value: LinkedInCopy[K]) {
    if (!result) return;
    setResult({ ...result, fields: { ...result.fields, [key]: value } });
  }

  async function copyPost() {
    const tags = (result?.hashtags ?? []).map((h) => `#${h}`).join(" ");
    const text = tags ? `${body}\n\n${tags}` : body;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked — no-op */
    }
  }

  // ---- gates ----
  if (capsLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (!caps?.enabled) {
    return (
      <EmptyState
        icon={Sparkles}
        variant="ai"
        title="LinkedIn Studio is turned off"
        description="Ask an admin to enable it (set POSTER_ENABLED=true on the API). Once on, you can generate branded LinkedIn posters + captions here."
      />
    );
  }

  const imgSrc = result ? `${API_BASE}${result.image_url}` : null;

  return (
    <div className="flex flex-col gap-8" data-testid="linkedin-studio">
      <SectionHeading
        eyebrow="Create · LinkedIn"
        heading="LinkedIn Studio"
        description="Describe what you want to announce. We design a branded poster and write the post — ready to publish."
        size="lg"
      />

      {!caps.renderer_available && (
        <StatusPill tone="watch" size="sm">
          Image renderer not detected on the server — install a headless browser
          to enable posters.
        </StatusPill>
      )}

      {/* ---- compose form ---- */}
      <section className="card-surface flex flex-col gap-4 p-6 sm:p-7">
        <label className="flex flex-col gap-1.5">
          <span className="text-meta">What are you announcing?</span>
          <Textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            rows={2}
            placeholder="e.g. Launching weekend brunch + online ordering for our cafe"
            data-testid="poster-topic"
          />
        </label>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-meta">Goal (optional)</span>
            <Input
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="e.g. drive weekend reservations"
            />
          </label>
          <label className="flex items-center gap-2.5 self-end pb-2">
            <input
              type="checkbox"
              checked={genImage}
              onChange={(e) => setGenImage(e.target.checked)}
              className="h-4 w-4 accent-ai"
            />
            <span className="text-sm text-muted-foreground">
              Generate a business-specific image (recommended)
            </span>
          </label>
        </div>
        <div>
          <Button
            onClick={generate}
            disabled={busy !== null || topic.trim().length < 3}
            data-testid="poster-generate"
          >
            {busy === "compose" ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Wand2 className="mr-2 h-4 w-4" />
            )}
            Generate post
          </Button>
        </div>
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
      </section>

      {/* ---- result ---- */}
      {busy === "compose" && !result && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Skeleton className="aspect-square w-full rounded-xl" />
          <Skeleton className="h-72 w-full rounded-xl" />
        </div>
      )}

      {result && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* poster */}
          <div className="flex flex-col gap-3">
            <div className="card-surface relative overflow-hidden rounded-xl p-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imgSrc ?? ""}
                alt="Generated LinkedIn poster"
                className="w-full rounded-lg"
                data-testid="poster-image"
              />
              {busy === "render" && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                  <Loader2 className="h-7 w-7 animate-spin text-ai" />
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <Button asChild variant="outline" size="sm">
                <a href={imgSrc ?? "#"} download="linkedin-poster.png">
                  <Download className="mr-2 h-3.5 w-3.5" /> Download image
                </a>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => result && rerender(result.fields)}
                disabled={busy !== null}
              >
                <RefreshCw className="mr-2 h-3.5 w-3.5" /> Re-render
              </Button>
            </div>

            {/* edit headline → re-render */}
            <details className="card-surface rounded-xl p-4">
              <summary className="cursor-pointer text-sm font-medium text-foreground">
                Tweak the poster text
              </summary>
              <div className="mt-3 flex flex-col gap-3">
                <LabeledInput
                  label="Eyebrow"
                  value={result.fields.eyebrow}
                  onChange={(v) => setField("eyebrow", v)}
                />
                <div className="grid grid-cols-2 gap-3">
                  <LabeledInput
                    label="Headline (white)"
                    value={result.fields.headline_lead}
                    onChange={(v) => setField("headline_lead", v)}
                  />
                  <LabeledInput
                    label="Headline (accent)"
                    value={result.fields.headline_accent}
                    onChange={(v) => setField("headline_accent", v)}
                  />
                </div>
                <LabeledInput
                  label="Subheadline"
                  value={result.fields.subheadline}
                  onChange={(v) => setField("subheadline", v)}
                />
                <Button
                  size="sm"
                  onClick={() => rerender(result.fields)}
                  disabled={busy !== null}
                  className="self-start"
                >
                  {busy === "render" ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <ImageIcon className="mr-2 h-4 w-4" />
                  )}
                  Apply to image
                </Button>
              </div>
            </details>
          </div>

          {/* caption */}
          <div className="card-surface flex flex-col gap-3 p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-card-title text-foreground">Your LinkedIn post</h3>
              <Button size="sm" onClick={copyPost} data-testid="poster-copy">
                {copied ? (
                  <Check className="mr-2 h-3.5 w-3.5" />
                ) : (
                  <Copy className="mr-2 h-3.5 w-3.5" />
                )}
                {copied ? "Copied" : "Copy post"}
              </Button>
            </div>
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={12}
              className="resize-y font-[450] leading-relaxed"
              data-testid="poster-body"
            />
            {result.hashtags.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {result.hashtags.map((h) => (
                  <span
                    key={h}
                    className="rounded-full bg-ai/10 px-2.5 py-1 text-xs font-medium text-ai"
                  >
                    #{h}
                  </span>
                ))}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Tip: paste the post on LinkedIn and attach the downloaded image.
              Direct publishing is coming next.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-meta">{label}</span>
      <Input value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
