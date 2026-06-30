"use client";

/**
 * Admin-only notice shown when durable object storage isn't configured
 * (MEDIA_BACKEND=local in production). Explains why image generation +
 * asset exports are disabled and points to the fix. Renders nothing when
 * storage is fine, while loading, on error, or for non-admins — it's a
 * safety/ops notice, never a user-facing feature surface.
 *
 * The backend is the real gate (any file write returns a 409); this is the
 * proactive explanation so an admin understands the state before clicking.
 */

import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { api, type StorageStatus } from "@/lib/api";

export function ObjectStorageNotice() {
  const { can } = useTenant();
  const [status, setStatus] = useState<StorageStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.system
      .storage()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        // Non-blocking: if we can't read the capability, show nothing
        // rather than a misleading warning.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!status || status.media_persistence_available) return null;
  // Infra/ops concern — only surface it to admins (team.manage).
  if (!can("team.manage")) return null;

  return (
    <div
      role="alert"
      data-testid="object-storage-notice"
      className="mb-4 flex items-start gap-3 rounded-lg border border-watch-border bg-watch-soft/40 p-4 text-sm"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-watch" />
      <div className="flex flex-col gap-1">
        <p className="font-medium text-foreground">
          Object storage isn&apos;t configured — image generation and asset
          exports are disabled.
        </p>
        <p className="text-muted-foreground">
          Generated files would be lost on this environment, so those features
          stay off to protect your work. Strategy, AI copy, editing, and
          revision history all work normally. To enable image features, set{" "}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">
            MEDIA_BACKEND
          </code>{" "}
          to a durable store (e.g. Cloudflare R2) — see{" "}
          <span className="font-mono text-xs">
            docs/production/object-storage.md
          </span>
          .
        </p>
      </div>
    </div>
  );
}
