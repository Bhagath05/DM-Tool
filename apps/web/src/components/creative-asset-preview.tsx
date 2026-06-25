"use client";

import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { RenderedVisual } from "@/lib/api";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function absoluteMediaUrl(signedPath: string): string {
  return signedPath.startsWith("http") ? signedPath : `${API_BASE}${signedPath}`;
}

export function CreativeAssetPreview({
  images,
  className,
  alt = "Generated creative",
}: {
  images: { signed_url: string; width?: number; height?: number; slide_index?: number | null }[];
  className?: string;
  alt?: string;
}) {
  if (images.length === 0) return null;

  if (images.length === 1) {
    const img = images[0]!;
    const src = absoluteMediaUrl(img.signed_url);
    return (
      <div className={cn("space-y-2", className)}>
        <div className="overflow-hidden rounded-md border bg-black/5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={src} alt={alt} className="w-full" loading="lazy" />
        </div>
        <AssetMeta src={src} width={img.width} height={img.height} />
      </div>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {images.map((img, i) => {
          const src = absoluteMediaUrl(img.signed_url);
          return (
            <div
              key={`${img.signed_url}-${i}`}
              className="min-w-[140px] max-w-[200px] shrink-0 space-y-1"
            >
              <div className="overflow-hidden rounded-md border bg-black/5">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={src}
                  alt={`${alt} slide ${(img.slide_index ?? i) + 1}`}
                  className="aspect-square w-full object-cover"
                  loading="lazy"
                />
              </div>
              <p className="text-center text-[10px] text-muted-foreground">
                Slide {(img.slide_index ?? i) + 1}
              </p>
              <Button asChild size="sm" variant="outline" className="w-full">
                <a href={src} download>
                  <Download className="h-3 w-3" />
                </a>
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AssetMeta({
  src,
  width,
  height,
}: {
  src: string;
  width?: number;
  height?: number;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
      <span>
        {width && height ? `${width}×${height}` : "PNG"} · ready to download
      </span>
      <Button asChild size="sm" variant="outline">
        <a href={src} download>
          <Download className="h-3.5 w-3.5" />
          Download
        </a>
      </Button>
    </div>
  );
}

export function rendersFromVisual(item: {
  renders?: RenderedVisual[];
  primary_signed_url?: string | null;
  thumbnail_url?: string | null;
}): RenderedVisual[] {
  if (item.renders && item.renders.length > 0) return item.renders;
  const url = item.primary_signed_url ?? item.thumbnail_url;
  if (!url) return [];
  return [
    {
      id: "primary",
      visual_id: "",
      provider: "openai",
      width: 0,
      height: 0,
      mime_type: "image/png",
      cost_cents: 0,
      latency_ms: 0,
      created_at: new Date().toISOString(),
      signed_url: url,
      slide_index: null,
    },
  ];
}
