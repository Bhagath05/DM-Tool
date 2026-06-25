"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { AdType } from "@/lib/api";

/** Type-narrow helpers — backend stores `output` as a free-form dict. */

type MetaVariant = { hook: string; headline: string };
type MetaAd = {
  primary_text: string;
  headline: string;
  description: string;
  cta_button: string;
  creative_direction: string;
  variants: MetaVariant[];
};

type GoogleAd = {
  headlines: string[];
  descriptions: string[];
  display_path: string;
  keyword_themes: string[];
};

type IgPromoAd = {
  hook: string;
  caption: string;
  on_screen_text: string[];
  cta_sticker_text: string;
  creative_direction: string;
  music_mood: string;
};

type LinkedInAd = {
  intro_text: string;
  headline: string;
  description: string;
  cta_button: string;
  creative_direction: string;
  professional_angle: string;
};

type YouTubeAdHook = { hook: string; angle: string };
type YouTubeAd = {
  headline: string;
  primary_text: string;
  description: string;
  cta_button: string;
  hook_variants: YouTubeAdHook[];
  creative_direction: string;
  video_format: string;
};

export function AdRenderer({
  adType,
  output,
}: {
  adType: AdType;
  output: Record<string, unknown>;
}) {
  switch (adType) {
    case "meta":
      return <RenderMeta data={output as unknown as MetaAd} />;
    case "google_search":
      return <RenderGoogle data={output as unknown as GoogleAd} />;
    case "instagram_promo":
      return <RenderIgPromo data={output as unknown as IgPromoAd} />;
    case "linkedin":
      return <RenderLinkedIn data={output as unknown as LinkedInAd} />;
    case "youtube":
      return <RenderYouTube data={output as unknown as YouTubeAd} />;
  }
}

/** Plain-text serializer used by the Copy button. */
export function serializeForCopy(
  adType: AdType,
  output: Record<string, unknown>,
): string {
  switch (adType) {
    case "meta": {
      const d = output as unknown as MetaAd;
      const variants = d.variants
        .map((v, i) => `  ${i + 1}. ${v.hook} | ${v.headline}`)
        .join("\n");
      return (
        `PRIMARY TEXT:\n${d.primary_text}\n\nHEADLINE: ${d.headline}\n` +
        `DESCRIPTION: ${d.description}\nCTA: ${d.cta_button}\n\n` +
        `VARIANTS:\n${variants}\n\nCREATIVE: ${d.creative_direction}`
      );
    }
    case "google_search": {
      const d = output as unknown as GoogleAd;
      const heads = d.headlines.map((h, i) => `  ${i + 1}. ${h}`).join("\n");
      const descs = d.descriptions
        .map((dd, i) => `  ${i + 1}. ${dd}`)
        .join("\n");
      return (
        `HEADLINES (${d.headlines.length}):\n${heads}\n\n` +
        `DESCRIPTIONS (${d.descriptions.length}):\n${descs}\n\n` +
        `DISPLAY PATH: /${d.display_path}\n\n` +
        `KEYWORD THEMES: ${d.keyword_themes.join(", ")}`
      );
    }
    case "instagram_promo": {
      const d = output as unknown as IgPromoAd;
      const overlays = d.on_screen_text
        .map((t, i) => `  ${i + 1}. ${t}`)
        .join("\n");
      return (
        `HOOK: ${d.hook}\n\nCAPTION:\n${d.caption}\n\n` +
        `ON-SCREEN TEXT:\n${overlays}\n\nCTA STICKER: ${d.cta_sticker_text}\n\n` +
        `CREATIVE: ${d.creative_direction}\nMUSIC MOOD: ${d.music_mood}`
      );
    }
    case "linkedin": {
      const d = output as unknown as LinkedInAd;
      return (
        `INTRO TEXT:\n${d.intro_text}\n\nHEADLINE: ${d.headline}\n` +
        `DESCRIPTION: ${d.description}\nCTA: ${d.cta_button}\n\n` +
        `CREATIVE: ${d.creative_direction}\n` +
        `PROFESSIONAL ANGLE: ${d.professional_angle}`
      );
    }
    case "youtube": {
      const d = output as unknown as YouTubeAd;
      const hooks = d.hook_variants
        .map((h, i) => `  ${i + 1}. ${h.hook}\n     (${h.angle})`)
        .join("\n");
      return (
        `HEADLINE: ${d.headline}\n\nSCRIPT OUTLINE:\n${d.primary_text}\n\n` +
        `DESCRIPTION: ${d.description}\nCTA: ${d.cta_button}\n\n` +
        `HOOK VARIANTS:\n${hooks}\n\nCREATIVE: ${d.creative_direction}\n` +
        `FORMAT: ${d.video_format}`
      );
    }
  }
}

// ----------------- per-platform renderers -----------------

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1.5 text-sm leading-relaxed">{children}</div>
    </div>
  );
}

function CtaPill({ label }: { label: string }) {
  return (
    <span className="rounded-md bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
      {label}
    </span>
  );
}

function RenderMeta({ data }: { data: MetaAd }) {
  return (
    <div className="space-y-4">
      <Field label="Primary text">
        <p className="whitespace-pre-wrap">{data.primary_text}</p>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Headline">
          <span className="font-semibold">{data.headline}</span>
        </Field>
        <Field label="Description">{data.description}</Field>
      </div>
      <Field label="CTA button">
        <CtaPill label={data.cta_button} />
      </Field>
      <Field label="Creative direction">
        <p className="text-muted-foreground">{data.creative_direction}</p>
      </Field>
      <Field label="A/B variants">
        <div className="grid gap-2 sm:grid-cols-2">
          {data.variants.map((v, i) => (
            <Card key={i}>
              <CardContent className="space-y-1 pt-4 text-xs">
                <div className="font-medium uppercase tracking-wide text-muted-foreground">
                  Variant {i + 1}
                </div>
                <div className="text-sm">{v.hook}</div>
                <div className="text-sm font-semibold">{v.headline}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      </Field>
    </div>
  );
}

function RenderGoogle({ data }: { data: GoogleAd }) {
  return (
    <div className="space-y-4">
      <Field label={`Headlines (${data.headlines.length})`}>
        <div className="flex flex-wrap gap-1.5">
          {data.headlines.map((h, i) => (
            <span
              key={i}
              className="rounded-md border border-input bg-card px-2 py-1 text-xs"
            >
              {h}
              <span className="ml-1 text-muted-foreground">
                ({h.length})
              </span>
            </span>
          ))}
        </div>
      </Field>
      <Field label={`Descriptions (${data.descriptions.length})`}>
        <ul className="space-y-1.5">
          {data.descriptions.map((d, i) => (
            <li key={i} className="rounded-md border border-input bg-card px-3 py-1.5 text-xs">
              {d}
              <span className="ml-1 text-muted-foreground">({d.length})</span>
            </li>
          ))}
        </ul>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Display path">
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
            yourbrand.com/{data.display_path}
          </code>
        </Field>
        <Field label="Keyword themes">
          <div className="flex flex-wrap gap-1.5">
            {data.keyword_themes.map((k) => (
              <span key={k} className="rounded-md bg-muted px-2 py-0.5 text-xs">
                {k}
              </span>
            ))}
          </div>
        </Field>
      </div>
    </div>
  );
}

function RenderIgPromo({ data }: { data: IgPromoAd }) {
  return (
    <div className="space-y-4">
      <Field label="Hook (first 1-3 seconds)">
        <span className="font-medium">{data.hook}</span>
      </Field>
      <Field label="Caption">
        <p className="whitespace-pre-wrap">{data.caption}</p>
      </Field>
      <Field label="On-screen text (in order)">
        <ol className="list-decimal space-y-1 pl-4">
          {data.on_screen_text.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ol>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="CTA sticker">
          <CtaPill label={data.cta_sticker_text} />
        </Field>
        <Field label="Music mood">
          <span className="text-muted-foreground">{data.music_mood}</span>
        </Field>
      </div>
      <Field label="Creative direction">
        <p className="text-muted-foreground">{data.creative_direction}</p>
      </Field>
    </div>
  );
}

function RenderLinkedIn({ data }: { data: LinkedInAd }) {
  return (
    <div className="space-y-4">
      <Field label="Intro text">
        <p className="whitespace-pre-wrap">{data.intro_text}</p>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Headline">
          <span className="font-semibold">{data.headline}</span>
        </Field>
        <Field label="Description">{data.description}</Field>
      </div>
      <Field label="CTA button">
        <CtaPill label={data.cta_button} />
      </Field>
      <Field label="Creative direction">
        <p className="text-muted-foreground">{data.creative_direction}</p>
      </Field>
      <Field label="Professional angle">
        <p>{data.professional_angle}</p>
      </Field>
    </div>
  );
}

function RenderYouTube({ data }: { data: YouTubeAd }) {
  return (
    <div className="space-y-4">
      <Field label="Headline (companion banner)">
        <span className="font-semibold">{data.headline}</span>
      </Field>
      <Field label="Script outline (6–15s)">
        <p className="whitespace-pre-wrap">{data.primary_text}</p>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Description">{data.description}</Field>
        <Field label="Format">
          <span className="capitalize">{data.video_format.replace(/_/g, " ")}</span>
        </Field>
      </div>
      <Field label="CTA button">
        <CtaPill label={data.cta_button} />
      </Field>
      <Field label="Hook variants (skippable at 5s)">
        <ol className="ml-4 list-decimal space-y-1.5">
          {data.hook_variants.map((h, i) => (
            <li key={i}>
              <span className="font-medium">{h.hook}</span>
              <span className="text-muted-foreground"> — {h.angle}</span>
            </li>
          ))}
        </ol>
      </Field>
      <Field label="Creative direction">
        <p className="text-muted-foreground">{data.creative_direction}</p>
      </Field>
    </div>
  );
}
