"use client";

import { ExternalLink, FileText, Loader2, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type LandingPage } from "@/lib/api";

import { CreateDialog } from "./create-dialog";

export function LandingPagesList() {
  const [pages, setPages] = useState<LandingPage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = async () => {
    try {
      const items = await api.landingPages.list();
      setPages(items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (error) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-destructive">
          {error}
        </CardContent>
      </Card>
    );
  }

  if (pages === null) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading pages…
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {pages.length === 0
            ? "No pages yet."
            : `${pages.length} page${pages.length === 1 ? "" : "s"}`}
        </p>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" />
          New page
        </Button>
      </div>

      {pages.length === 0 ? (
        <EmptyState onCreate={() => setCreating(true)} />
      ) : (
        <div className="grid gap-3">
          {pages.map((p) => (
            <PageRow key={p.id} page={p} />
          ))}
        </div>
      )}

      {creating && (
        <CreateDialog
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileText className="h-4 w-4 text-muted-foreground" />
          Create your first lead page
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          A single-purpose conversion page with a form. Share the URL from any
          campaign, ad, post, or DM — submissions land in your inbox.
        </p>
        <Button onClick={onCreate}>
          <Plus className="h-4 w-4" />
          New page
        </Button>
      </CardContent>
    </Card>
  );
}

function PageRow({ page }: { page: LandingPage }) {
  const publicUrl = `/p/${page.slug}${page.status === "draft" ? `?preview=${page.preview_token}` : ""}`;
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-4 pt-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Link
              href={`/landing-pages/${page.id}` as never}
              className="text-sm font-semibold hover:underline"
            >
              {page.title}
            </Link>
            <StatusBadge status={page.status} />
          </div>
          <div className="mt-0.5 truncate text-xs text-muted-foreground">
            /p/{page.slug}
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <Stat label="Views" value={page.view_count} />
          <Stat label="Leads" value={page.submission_count} />
        </div>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={publicUrl} target="_blank" rel="noreferrer">
              <ExternalLink className="h-3.5 w-3.5" />
              Open
            </a>
          </Button>
          <Button asChild size="sm">
            <Link href={`/landing-pages/${page.id}` as never}>Edit</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center">
      <div className="font-mono text-sm font-semibold text-foreground">
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wide">{label}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: "draft" | "published" }) {
  return (
    <span
      className={
        status === "published"
          ? "rounded bg-green-600/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-green-700 dark:text-green-400"
          : "rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
      }
    >
      {status}
    </span>
  );
}
