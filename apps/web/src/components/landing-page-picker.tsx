"use client";

import { ExternalLink, FileX, Globe, Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Label } from "@/components/ui/label";
import { api, type LandingPage } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Shared landing-page chooser used by every generator studio (content / ads /
 * visuals / campaigns). The whole point of Phase 1.7.1 is to close the funnel
 * — every asset should *optionally* attach to a published landing page so the
 * generated share URL carries full attribution back to a captured lead.
 *
 * Self-contained: fetches the user's pages, handles loading + empty states,
 * and surfaces a quick link to /landing-pages for creating new ones.
 *
 * Returns the page id (or null) via onChange. The caller persists nothing
 * locally — the picker is stateless from its parent's perspective.
 */
export function LandingPagePicker({
  value,
  onChange,
  helperText,
}: {
  value: string | null;
  onChange: (id: string | null) => void;
  helperText?: string;
}) {
  const [state, setState] = useState<
    | { kind: "loading" }
    | { kind: "ready"; pages: LandingPage[] }
    | { kind: "error"; message: string }
  >({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const items = await api.landingPages.list();
        if (cancelled) return;
        // Show published first (drafts only show if explicitly attached later).
        const published = items.filter((p) => p.status === "published");
        setState({ kind: "ready", pages: published });
      } catch (e) {
        if (cancelled) return;
        setState({
          kind: "error",
          message: e instanceof Error ? e.message : "Couldn't load pages",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <Label>Attach a lead page (optional)</Label>
        <Link
          href={"/landing-pages" as never}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          Manage pages
          <ExternalLink className="h-3 w-3" />
        </Link>
      </div>
      <p className="text-xs text-muted-foreground">
        {helperText ??
          "We'll add a smart link to this asset so every customer who clicks gets tracked back to it. That's how you'll know what's actually working."}
      </p>

      {state.kind === "loading" && (
        <div className="flex items-center gap-2 rounded-md border border-dashed px-3 py-3 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Loading your pages…
        </div>
      )}

      {state.kind === "error" && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {state.message}
        </div>
      )}

      {state.kind === "ready" && state.pages.length === 0 && (
        <div className="flex items-center gap-3 rounded-md border border-dashed px-3 py-3">
          <FileX className="h-4 w-4 text-muted-foreground" />
          <div className="flex-1 text-xs text-muted-foreground">
            No published pages yet. Without one, this asset won&apos;t have a
            shareable lead-capture link.
          </div>
          <Link
            href={"/landing-pages" as never}
            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
          >
            Create one
            <ExternalLink className="h-3 w-3" />
          </Link>
        </div>
      )}

      {state.kind === "ready" && state.pages.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <PillButton
            active={value === null}
            onClick={() => onChange(null)}
            label="No page (skip attribution)"
          />
          {state.pages.map((p) => (
            <PillButton
              key={p.id}
              active={value === p.id}
              onClick={() => onChange(p.id)}
              icon={<Globe className="h-3 w-3" />}
              label={p.title}
              hint={`/p/${p.slug}`}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function PillButton({
  active,
  onClick,
  label,
  hint,
  icon,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  hint?: string;
  icon?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex max-w-[260px] items-center gap-2 rounded-md border px-3 py-1.5 text-left text-sm transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-input hover:bg-accent",
      )}
    >
      {icon}
      <span className="flex flex-col leading-tight">
        <span className="truncate">{label}</span>
        {hint && (
          <span
            className={cn(
              "text-[10px]",
              active ? "text-primary-foreground/80" : "text-muted-foreground",
            )}
          >
            {hint}
          </span>
        )}
      </span>
    </button>
  );
}
