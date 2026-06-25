"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { ColorSwatch, TypographyHint, VisualType } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Per-type output shapes (server stores `output` as a free-form dict). */

type AdCreative = {
  aspect_ratio: string;
  focal_subject: string;
  composition_layout: string;
  color_palette: ColorSwatch[];
  typography: TypographyHint;
  visual_hierarchy: string[];
  cta_placement: string;
  mood_keywords: string[];
  reference_aesthetic: string;
};

type CarouselSlide = {
  slide_number: number;
  visual: string;
  text_treatment: string;
  transition_to_next: string;
};
type CarouselPlan = {
  aspect_ratio: string;
  cover_concept: string;
  design_system_palette: ColorSwatch[];
  design_system_typography: TypographyHint;
  slide_designs: CarouselSlide[];
  cta_slide_concept: string;
};

type ReelScene = {
  scene_number: number;
  timestamp_range: string;
  shot_type: string;
  framing: string;
  motion: string;
  overlay_text: string;
};
type ReelPlan = {
  aspect_ratio: string;
  visual_style: string;
  scenes: ReelScene[];
  text_overlay_style: TypographyHint;
  music_visual_sync: string;
  color_grading: string;
};

type Thumbnail = {
  aspect_ratio: string;
  focal_subject: string;
  contrast_strategy: string;
  text_overlay: string;
  typography: TypographyHint;
  background_treatment: string;
  mobile_legibility_note: string;
};

export function VisualRenderer({
  visualType,
  output,
}: {
  visualType: VisualType;
  output: Record<string, unknown>;
}) {
  switch (visualType) {
    case "ad_creative":
      return <RenderAdCreative data={output as unknown as AdCreative} />;
    case "carousel":
      return <RenderCarousel data={output as unknown as CarouselPlan} />;
    case "reel":
      return <RenderReel data={output as unknown as ReelPlan} />;
    case "thumbnail":
      return <RenderThumbnail data={output as unknown as Thumbnail} />;
  }
}

export function serializeForCopy(
  visualType: VisualType,
  output: Record<string, unknown>,
): string {
  const fmtPalette = (p: ColorSwatch[]) =>
    p.map((c) => `  ${c.role.padEnd(11)}  ${c.hex}  ${c.name}`).join("\n");
  const fmtType = (t: TypographyHint) =>
    `  style:    ${t.style}\n  headline: ${t.headline_treatment}\n  body:     ${t.body_treatment}\n  fonts:    ${t.suggested_fonts.join(", ")}`;

  switch (visualType) {
    case "ad_creative": {
      const d = output as unknown as AdCreative;
      const hierarchy = d.visual_hierarchy.map((h, i) => `  ${i + 1}. ${h}`).join("\n");
      return (
        `ASPECT: ${d.aspect_ratio}\nFOCAL SUBJECT: ${d.focal_subject}\n` +
        `LAYOUT: ${d.composition_layout}\n\n` +
        `COLOR PALETTE:\n${fmtPalette(d.color_palette)}\n\n` +
        `TYPOGRAPHY:\n${fmtType(d.typography)}\n\n` +
        `VISUAL HIERARCHY:\n${hierarchy}\n\n` +
        `CTA PLACEMENT: ${d.cta_placement}\n` +
        `MOOD: ${d.mood_keywords.join(", ")}\n` +
        `REFERENCE: ${d.reference_aesthetic}`
      );
    }
    case "carousel": {
      const d = output as unknown as CarouselPlan;
      const slides = d.slide_designs
        .map(
          (s) =>
            `  Slide ${s.slide_number}\n   visual:     ${s.visual}\n   text:       ${s.text_treatment}\n   transition: ${s.transition_to_next}`,
        )
        .join("\n\n");
      return (
        `ASPECT: ${d.aspect_ratio}\nCOVER: ${d.cover_concept}\n\n` +
        `DESIGN-SYSTEM PALETTE:\n${fmtPalette(d.design_system_palette)}\n\n` +
        `DESIGN-SYSTEM TYPOGRAPHY:\n${fmtType(d.design_system_typography)}\n\n` +
        `SLIDES:\n${slides}\n\n` +
        `CTA SLIDE: ${d.cta_slide_concept}`
      );
    }
    case "reel": {
      const d = output as unknown as ReelPlan;
      const scenes = d.scenes
        .map(
          (s) =>
            `  Scene ${s.scene_number} (${s.timestamp_range})\n   shot:    ${s.shot_type}\n   framing: ${s.framing}\n   motion:  ${s.motion}\n   text:    ${s.overlay_text}`,
        )
        .join("\n\n");
      return (
        `ASPECT: ${d.aspect_ratio}\nSTYLE: ${d.visual_style}\n` +
        `COLOR GRADING: ${d.color_grading}\nMUSIC SYNC: ${d.music_visual_sync}\n\n` +
        `SCENES:\n${scenes}\n\n` +
        `OVERLAY TYPOGRAPHY:\n${fmtType(d.text_overlay_style)}`
      );
    }
    case "thumbnail": {
      const d = output as unknown as Thumbnail;
      return (
        `ASPECT: ${d.aspect_ratio}\nFOCAL: ${d.focal_subject}\n` +
        `CONTRAST: ${d.contrast_strategy}\n` +
        `TEXT OVERLAY: ${d.text_overlay}\n\n` +
        `TYPOGRAPHY:\n${fmtType(d.typography)}\n\n` +
        `BACKGROUND: ${d.background_treatment}\n` +
        `MOBILE LEGIBILITY: ${d.mobile_legibility_note}`
      );
    }
  }
}

// ----------------- shared building blocks -----------------

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

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-md bg-muted px-2 py-0.5 text-xs">{children}</span>
  );
}

function PaletteRow({ palette }: { palette: ColorSwatch[] }) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {palette.map((c) => (
          <div
            key={c.hex + c.name}
            className="overflow-hidden rounded-md border border-border"
          >
            <div className="h-14" style={{ background: c.hex }} />
            <div className="space-y-0.5 p-2 text-xs">
              <div className="font-medium">{c.name}</div>
              <div className="font-mono text-muted-foreground">
                {c.hex.toUpperCase()}
              </div>
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                {c.role}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TypographyCard({ t }: { t: TypographyHint }) {
  return (
    <Card>
      <CardContent className="space-y-2 pt-4 text-sm">
        <div className="text-base font-semibold leading-tight">{t.style}</div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div>
            <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Headline
            </div>
            <div className="text-xs">{t.headline_treatment}</div>
          </div>
          <div>
            <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Body
            </div>
            <div className="text-xs">{t.body_treatment}</div>
          </div>
        </div>
        <div>
          <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Font suggestions
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {t.suggested_fonts.map((f) => (
              <Pill key={f}>{f}</Pill>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function AspectBadge({ aspect }: { aspect: string }) {
  return (
    <span
      className={cn(
        "rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide",
      )}
    >
      {aspect}
    </span>
  );
}

// ----------------- per-type renderers -----------------

function RenderAdCreative({ data }: { data: AdCreative }) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <AspectBadge aspect={data.aspect_ratio} />
        {data.mood_keywords.map((m) => (
          <Pill key={m}>{m}</Pill>
        ))}
      </div>
      <Field label="Focal subject">{data.focal_subject}</Field>
      <Field label="Composition layout">{data.composition_layout}</Field>
      <Field label="Color palette">
        <PaletteRow palette={data.color_palette} />
      </Field>
      <Field label="Typography">
        <TypographyCard t={data.typography} />
      </Field>
      <Field label="Visual hierarchy">
        <ol className="space-y-1 list-decimal pl-4">
          {data.visual_hierarchy.map((h, i) => (
            <li key={i}>{h}</li>
          ))}
        </ol>
      </Field>
      <Field label="CTA placement">{data.cta_placement}</Field>
      <Field label="Reference aesthetic">
        <span className="text-muted-foreground">{data.reference_aesthetic}</span>
      </Field>
    </div>
  );
}

function RenderCarousel({ data }: { data: CarouselPlan }) {
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <AspectBadge aspect={data.aspect_ratio} />
      </div>
      <Field label="Cover (slide 1)">{data.cover_concept}</Field>
      <Field label="Design-system palette">
        <PaletteRow palette={data.design_system_palette} />
      </Field>
      <Field label="Design-system typography">
        <TypographyCard t={data.design_system_typography} />
      </Field>
      <Field label={`Slides (${data.slide_designs.length})`}>
        <div className="grid gap-2 sm:grid-cols-2">
          {data.slide_designs.map((s) => (
            <Card key={s.slide_number}>
              <CardContent className="space-y-1.5 pt-4 text-xs">
                <div className="font-medium uppercase tracking-wide text-muted-foreground">
                  Slide {s.slide_number}
                </div>
                <div className="text-sm">{s.visual}</div>
                <div className="text-muted-foreground">
                  <span className="font-medium text-foreground/80">Text:</span>{" "}
                  {s.text_treatment}
                </div>
                <div className="text-muted-foreground">
                  <span className="font-medium text-foreground/80">→ Next:</span>{" "}
                  {s.transition_to_next}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </Field>
      <Field label="CTA slide">{data.cta_slide_concept}</Field>
    </div>
  );
}

function RenderReel({ data }: { data: ReelPlan }) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <AspectBadge aspect={data.aspect_ratio} />
        <Pill>{data.visual_style}</Pill>
      </div>
      <Field label={`Scenes (${data.scenes.length})`}>
        <div className="space-y-2">
          {data.scenes.map((s) => (
            <Card key={s.scene_number}>
              <CardContent className="grid gap-1 pt-4 text-xs sm:grid-cols-[80px_1fr]">
                <div className="font-mono uppercase tracking-wide text-muted-foreground">
                  {s.timestamp_range}
                </div>
                <div className="space-y-1">
                  <div className="text-sm font-medium">
                    Scene {s.scene_number} · {s.shot_type}
                  </div>
                  <div className="text-muted-foreground">
                    <span className="font-medium text-foreground/80">Framing:</span>{" "}
                    {s.framing}
                  </div>
                  <div className="text-muted-foreground">
                    <span className="font-medium text-foreground/80">Motion:</span>{" "}
                    {s.motion}
                  </div>
                  <div className="text-muted-foreground">
                    <span className="font-medium text-foreground/80">Overlay:</span>{" "}
                    {s.overlay_text}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </Field>
      <Field label="Color grading">
        <span className="text-muted-foreground">{data.color_grading}</span>
      </Field>
      <Field label="Music ↔ visual sync">
        <span className="text-muted-foreground">{data.music_visual_sync}</span>
      </Field>
      <Field label="Overlay typography">
        <TypographyCard t={data.text_overlay_style} />
      </Field>
    </div>
  );
}

function RenderThumbnail({ data }: { data: Thumbnail }) {
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <AspectBadge aspect={data.aspect_ratio} />
      </div>
      <Field label="Focal subject">{data.focal_subject}</Field>
      <Field label="Contrast strategy">{data.contrast_strategy}</Field>
      <Field label="Text overlay">
        <span className="font-medium">{data.text_overlay}</span>
      </Field>
      <Field label="Typography">
        <TypographyCard t={data.typography} />
      </Field>
      <Field label="Background treatment">{data.background_treatment}</Field>
      <Field label="Mobile legibility">
        <span className="text-muted-foreground">
          {data.mobile_legibility_note}
        </span>
      </Field>
    </div>
  );
}
