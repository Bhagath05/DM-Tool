"use client";

import { AlertTriangle, Check, Copy, ExternalLink, Link2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";

/**
 * The distribution surface that ships with every generated asset.
 *
 * Two states:
 * - `url` present  → render the attributed share URL with a copy button. This
 *   is what the user paste into their post / ad / story.
 * - `url` absent   → render a soft warning: this asset can't capture leads,
 *   here's the one-click path to fix that.
 *
 * The point is to make it impossible to ignore the funnel — every result the
 * studio produces nudges the user toward attaching a landing page.
 */
export function ShareUrlBlock({ url }: { url: string | null }) {
  const [copied, setCopied] = useState(false);

  if (!url) {
    return (
      <div className="flex flex-wrap items-start gap-3 rounded-md border border-amber-300/40 bg-amber-50/60 px-3 py-2.5 dark:bg-amber-950/20">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <div className="flex-1 text-xs">
          <div className="font-medium text-amber-900 dark:text-amber-200">
            No lead page attached
          </div>
          <p className="mt-0.5 text-amber-800/80 dark:text-amber-300/80">
            Without one, we can&apos;t tell which customers came from this.
            Attach a page next time you generate and the link below will
            do the tracking automatically.
          </p>
        </div>
        <Link
          href={"/landing-pages" as never}
          className="inline-flex shrink-0 items-center gap-1 rounded-md border border-amber-400/50 bg-white px-2.5 py-1 text-xs font-medium text-amber-900 hover:bg-amber-50 dark:bg-amber-950/40 dark:text-amber-200"
        >
          Manage pages
          <ExternalLink className="h-3 w-3" />
        </Link>
      </div>
    );
  }

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* ignore — older browsers */
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/30 px-3 py-2.5">
      <Link2 className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Use this link when you post
        </div>
        <code className="block truncate text-xs">{url}</code>
      </div>
      <Button variant="outline" size="sm" onClick={onCopy}>
        {copied ? (
          <Check className="h-3.5 w-3.5" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
        {copied ? "Copied" : "Copy"}
      </Button>
      <a
        href={url}
        target="_blank"
        rel="noreferrer noopener"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        Open
        <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}
