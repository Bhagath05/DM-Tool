"use client";

import { Hash } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { ContentType } from "@/lib/api";

/** Type-narrow helpers — backend stores `output` as a free-form dict. */

type SocialPost = {
  hook: string;
  body: string;
  hashtags: string[];
  cta: string;
};

type ReelBeat = { label: string; description: string };
type Reel = {
  hook: string;
  beats: ReelBeat[];
  on_screen_text: string[];
  caption: string;
  hashtags: string[];
  cta: string;
};

type CarouselSlide = { title: string; body: string };
type Carousel = {
  cover_title: string;
  slides: CarouselSlide[];
  caption: string;
  hashtags: string[];
  cta: string;
};

type AdCopy = {
  headline: string;
  primary_text: string;
  description: string;
  cta_button: string;
  targeting_note: string;
};

export function ContentRenderer({
  contentType,
  output,
}: {
  contentType: ContentType;
  output: Record<string, unknown>;
}) {
  switch (contentType) {
    case "social_post":
      return <RenderSocialPost data={output as unknown as SocialPost} />;
    case "reel":
      return <RenderReel data={output as unknown as Reel} />;
    case "carousel":
      return <RenderCarousel data={output as unknown as Carousel} />;
    case "ad_copy":
      return <RenderAdCopy data={output as unknown as AdCopy} />;
    default:
      // Phase 6.2 — written / long-form / micro-copy types render generically
      // from their structured output (no bespoke per-type component needed).
      return <RenderGeneric data={output} />;
  }
}

/** Generic structured-output renderer for content types without a bespoke
 * component. Walks the output dict and renders labelled text + lists. */
function RenderGeneric({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([k]) => k !== "creative_brief");
  return (
    <div className="space-y-3 text-sm">
      {entries.map(([key, value]) => (
        <div key={key} className="space-y-1">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {key.replace(/_/g, " ")}
          </div>
          <GenericValue value={value} />
        </div>
      ))}
    </div>
  );
}

function GenericValue({ value }: { value: unknown }) {
  if (value == null) return <span className="text-muted-foreground">—</span>;
  if (typeof value === "string" || typeof value === "number")
    return <p className="whitespace-pre-wrap leading-relaxed">{String(value)}</p>;
  if (Array.isArray(value))
    return (
      <ul className="list-disc space-y-1 pl-5">
        {value.map((v, i) => (
          <li key={i}>
            <GenericValue value={v} />
          </li>
        ))}
      </ul>
    );
  if (typeof value === "object")
    return (
      <div className="space-y-1 rounded-md border border-border/60 p-2">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k}>
            <span className="text-xs text-muted-foreground">
              {k.replace(/_/g, " ")}:{" "}
            </span>
            <GenericValue value={v} />
          </div>
        ))}
      </div>
    );
  return <span>{String(value)}</span>;
}

/** Plain-text serializer used by the Copy button. */
export function serializeForCopy(
  contentType: ContentType,
  output: Record<string, unknown>,
): string {
  switch (contentType) {
    case "social_post": {
      const d = output as unknown as SocialPost;
      return `${d.hook}\n\n${d.body}\n\n${d.cta}\n\n${tagLine(d.hashtags)}`;
    }
    case "reel": {
      const d = output as unknown as Reel;
      const beats = d.beats.map((b, i) => `${i + 1}. ${b.label} — ${b.description}`).join("\n");
      const overlays = d.on_screen_text.map((t, i) => `${i + 1}. ${t}`).join("\n");
      return (
        `HOOK: ${d.hook}\n\nBEATS:\n${beats}\n\nON-SCREEN TEXT:\n${overlays}\n\n` +
        `CAPTION:\n${d.caption}\n\nCTA: ${d.cta}\n\n${tagLine(d.hashtags)}`
      );
    }
    case "carousel": {
      const d = output as unknown as Carousel;
      const slides = d.slides
        .map((s, i) => `Slide ${i + 2}: ${s.title}\n${s.body}`)
        .join("\n\n");
      return (
        `Slide 1 (Cover): ${d.cover_title}\n\n${slides}\n\n` +
        `Caption:\n${d.caption}\n\nCTA: ${d.cta}\n\n${tagLine(d.hashtags)}`
      );
    }
    case "ad_copy": {
      const d = output as unknown as AdCopy;
      return (
        `Headline: ${d.headline}\n\nPrimary text:\n${d.primary_text}\n\n` +
        `Description: ${d.description}\nCTA button: ${d.cta_button}\n\n` +
        `Targeting: ${d.targeting_note}`
      );
    }
    default:
      // Phase 6.2 — generic serialization for the written / long-form types.
      return genericSerialize(output);
  }
}

/** Flatten any structured output into readable labelled text for the clipboard. */
function genericSerialize(output: Record<string, unknown>): string {
  const parts: string[] = [];
  const walk = (label: string, v: unknown) => {
    if (label === "creative_brief" || label === "strategy") return;
    if (v == null) return;
    if (typeof v === "string" || typeof v === "number")
      parts.push(`${label ? label.replace(/_/g, " ").toUpperCase() + ": " : ""}${v}`);
    else if (Array.isArray(v))
      v.forEach((x, i) => walk(`${label} ${i + 1}`.trim(), x));
    else if (typeof v === "object")
      Object.entries(v as Record<string, unknown>).forEach(([k, x]) => walk(k, x));
  };
  Object.entries(output).forEach(([k, v]) => walk(k, v));
  return parts.join("\n\n");
}

const tagLine = (hashtags: string[]) =>
  hashtags.map((h) => (h.startsWith("#") ? h : `#${h}`)).join(" ");

// ----------------- per-type renderers -----------------

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1.5 text-sm leading-relaxed">{children}</div>
    </div>
  );
}

function HashtagRow({ hashtags }: { hashtags: string[] }) {
  return (
    <div>
      <div className="flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Hash className="h-3 w-3" /> Hashtags
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {hashtags.map((h) => (
          <span
            key={h}
            className="rounded-md bg-muted px-2 py-0.5 text-xs"
          >
            {h.startsWith("#") ? h : `#${h}`}
          </span>
        ))}
      </div>
    </div>
  );
}

function RenderSocialPost({ data }: { data: SocialPost }) {
  return (
    <div className="space-y-4">
      <Section label="Hook">
        <span className="font-medium">{data.hook}</span>
      </Section>
      <Section label="Body">
        <p className="whitespace-pre-wrap">{data.body}</p>
      </Section>
      <Section label="CTA">{data.cta}</Section>
      <HashtagRow hashtags={data.hashtags} />
    </div>
  );
}

function RenderReel({ data }: { data: Reel }) {
  return (
    <div className="space-y-4">
      <Section label="Hook (0-2s)">
        <span className="font-medium">{data.hook}</span>
      </Section>
      <Section label="Beats">
        <ol className="space-y-1.5">
          {data.beats.map((b, i) => (
            <li key={i}>
              <span className="font-medium">
                {i + 1}. {b.label}
              </span>{" "}
              <span className="text-muted-foreground">— {b.description}</span>
            </li>
          ))}
        </ol>
      </Section>
      <Section label="On-screen text">
        <ol className="list-decimal space-y-1 pl-4">
          {data.on_screen_text.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ol>
      </Section>
      <Section label="Caption">
        <p className="whitespace-pre-wrap">{data.caption}</p>
      </Section>
      <Section label="CTA">{data.cta}</Section>
      <HashtagRow hashtags={data.hashtags} />
    </div>
  );
}

function RenderCarousel({ data }: { data: Carousel }) {
  return (
    <div className="space-y-4">
      <Section label="Slide 1 — Cover">
        <span className="font-medium">{data.cover_title}</span>
      </Section>
      <div className="grid gap-2 sm:grid-cols-2">
        {data.slides.map((s, i) => (
          <Card key={i}>
            <CardContent className="space-y-1 pt-4">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Slide {i + 2}
              </div>
              <div className="text-sm font-medium">{s.title}</div>
              <div className="text-sm text-foreground/80">{s.body}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Section label="Caption">
        <p className="whitespace-pre-wrap">{data.caption}</p>
      </Section>
      <Section label="CTA">{data.cta}</Section>
      <HashtagRow hashtags={data.hashtags} />
    </div>
  );
}

function RenderAdCopy({ data }: { data: AdCopy }) {
  return (
    <div className="space-y-4">
      <Section label="Headline">
        <span className="text-base font-semibold">{data.headline}</span>
      </Section>
      <Section label="Primary text">
        <p className="whitespace-pre-wrap">{data.primary_text}</p>
      </Section>
      <Section label="Description">{data.description}</Section>
      <Section label="CTA button">
        <span className="rounded-md bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
          {data.cta_button}
        </span>
      </Section>
      <Section label="Targeting">
        <p className="text-muted-foreground">{data.targeting_note}</p>
      </Section>
    </div>
  );
}
