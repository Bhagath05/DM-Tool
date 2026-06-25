"use client";

/**
 * Settings · Organization — Danger Zone.
 *
 * Two owner-only destructive actions, each behind a type-to-confirm
 * modal so neither fires by accident:
 *
 *   Reset workspace  → POST /orgs/{id}/reset
 *       Wipes every piece of user-provided content (business profile,
 *       campaigns, content, leads, creatives, videos, social posts,
 *       trends, performance data, …) but KEEPS the workspace itself —
 *       org, members, roles, brands, billing, connections. The founder
 *       starts clean without re-creating the account. On success we hard
 *       reload so every page refetches from the now-empty backend.
 *
 *   Delete workspace → POST /orgs/{id}/purge
 *       HARD deletes the organization and everything in it via DB
 *       cascade. Irreversible. On success we drop the stale tenant
 *       selection and send the user back to onboarding.
 *
 * Visibility: only rendered for org owners. The backend independently
 * enforces owner-only, so this is purely to avoid showing a control the
 * user can't use.
 */

import { AlertTriangle, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { api, ApiError } from "@/lib/api";
import { clearPersistedSelection, setActiveTenantHeaders } from "@/lib/tenant";
import { cn } from "@/lib/utils";

type Pending = null | "reset" | "delete";

export function DangerZone() {
  const tenant = useTenant();
  const router = useRouter();

  const [open, setOpen] = useState<Pending>(null);
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const orgId = tenant.activeOrg?.id ?? null;
  const orgName = tenant.activeOrg?.name ?? "this workspace";
  const isOwner = tenant.roleSlugs?.includes("owner") ?? false;

  // Only owners get the danger zone (backend enforces this too).
  if (!orgId || !isOwner) return null;

  function closeModal() {
    if (busy) return;
    setOpen(null);
    setConfirmText("");
    setError(null);
  }

  // Confirmation phrase per action. Reset is a fixed keyword; delete
  // requires the exact org name so it can't be muscle-memoried.
  const resetPhrase = "RESET";
  const deletePhrase = orgName;
  const requiredPhrase = open === "delete" ? deletePhrase : resetPhrase;
  const confirmed =
    confirmText.trim().toLowerCase() === requiredPhrase.trim().toLowerCase();

  async function runReset() {
    if (!orgId) return;
    setBusy(true);
    setError(null);
    try {
      await api.orgs.reset(orgId);
      // Everything brand-scoped is gone; hard reload so the whole app
      // refetches against the empty workspace.
      window.location.assign("/");
    } catch (err) {
      setBusy(false);
      setError(
        err instanceof ApiError ? err.message : "Reset failed. Try again.",
      );
    }
  }

  async function runDelete() {
    if (!orgId) return;
    setBusy(true);
    setError(null);
    try {
      await api.orgs.purge(orgId);
      // The org (and our membership) no longer exists — drop the stale
      // selection so TenantProvider doesn't try to use a dead org id.
      clearPersistedSelection();
      setActiveTenantHeaders({ organization_id: null, brand_id: null });
      // Land back IN the app shell (not the full-screen wizard). With no
      // membership, RequireTenant renders the "Set up your workspace" card,
      // from which the user clicks "Create workspace" to enter the wizard.
      router.replace("/today");
      // Belt-and-braces: force a fresh load so TenantProvider re-runs /me.
      window.location.assign("/today");
    } catch (err) {
      setBusy(false);
      setError(
        err instanceof ApiError ? err.message : "Delete failed. Try again.",
      );
    }
  }

  return (
    <section
      data-testid="organization-danger-zone"
      className="flex flex-col gap-4 rounded-lg border border-destructive/40 bg-destructive/5 p-6 sm:p-7"
    >
      <header className="flex items-start gap-3">
        <span
          aria-hidden
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-destructive/15 text-destructive"
        >
          <AlertTriangle className="h-4.5 w-4.5" />
        </span>
        <div className="flex flex-col gap-0.5">
          <h3 className="text-card-title text-foreground">Danger zone</h3>
          <p className="text-sm text-muted-foreground">
            Destructive actions for <span className="font-medium">{orgName}</span>.
            Owner only. These can&apos;t be undone.
          </p>
        </div>
      </header>

      <div className="flex flex-col divide-y divide-destructive/15 border-t border-destructive/15">
        <DangerRow
          title="Reset workspace data"
          description="Delete your business profile and everything generated — campaigns, content, leads, creatives, videos. Keeps the workspace, team, brands, and billing."
          actionLabel="Reset data"
          icon={RotateCcw}
          onClick={() => setOpen("reset")}
        />
        <DangerRow
          title="Delete workspace"
          description="Permanently remove this organization and all of its data. There is no recovery."
          actionLabel="Delete workspace"
          icon={Trash2}
          destructive
          onClick={() => setOpen("delete")}
        />
      </div>

      {/* ---- Confirmation modal (shared shell for both actions) ---- */}
      <Modal
        open={open !== null}
        onOpenChange={(v) => (v ? undefined : closeModal())}
        title={
          open === "delete" ? "Delete this workspace?" : "Reset workspace data?"
        }
        description={
          open === "delete"
            ? "This permanently deletes the organization and everything in it."
            : "This clears all your content and your business profile. The workspace itself stays."
        }
        className="max-w-md"
        data-testid="danger-confirm-modal"
      >
        <div className="flex flex-col gap-4 p-5">
          <ul className="flex flex-col gap-1.5 text-sm text-muted-foreground">
            {(open === "delete"
              ? [
                  "The organization and every brand are removed.",
                  "All members lose access immediately.",
                  "Billing history and connections are deleted too.",
                ]
              : [
                  "Business profile + AI analysis cleared.",
                  "All campaigns, content, leads, and creatives removed.",
                  "Team, brands, billing, and connections are kept.",
                ]
            ).map((line) => (
              <li key={line} className="flex items-start gap-2">
                <span
                  aria-hidden
                  className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-destructive"
                />
                {line}
              </li>
            ))}
          </ul>

          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-muted-foreground">
              Type{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">
                {requiredPhrase}
              </code>{" "}
              to confirm
            </span>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={requiredPhrase}
              autoComplete="off"
              spellCheck={false}
              disabled={busy}
              data-testid="danger-confirm-input"
              onKeyDown={(e) => {
                if (e.key === "Enter" && confirmed && !busy) {
                  void (open === "delete" ? runDelete() : runReset());
                }
              }}
            />
          </label>

          {error && (
            <p
              className="text-sm text-destructive"
              role="alert"
              data-testid="danger-error"
            >
              {error}
            </p>
          )}

          <div className="flex items-center justify-end gap-2 pt-1">
            <Button variant="outline" onClick={closeModal} disabled={busy}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={!confirmed || busy}
              data-testid="danger-confirm-button"
              onClick={() =>
                void (open === "delete" ? runDelete() : runReset())
              }
            >
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {open === "delete" ? "Delete workspace" : "Reset data"}
            </Button>
          </div>
        </div>
      </Modal>
    </section>
  );
}

// ---------------------------------------------------------------------
//  Row
// ---------------------------------------------------------------------

function DangerRow({
  title,
  description,
  actionLabel,
  icon: Icon,
  destructive,
  onClick,
}: {
  title: string;
  description: string;
  actionLabel: string;
  icon: typeof RotateCcw;
  destructive?: boolean;
  onClick: () => void;
}) {
  return (
    <div className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-foreground">{title}</span>
        <span className="text-xs leading-relaxed text-muted-foreground">
          {description}
        </span>
      </div>
      <Button
        variant={destructive ? "destructive" : "outline"}
        size="sm"
        onClick={onClick}
        className={cn("shrink-0", !destructive && "border-destructive/40 text-destructive hover:bg-destructive/10")}
      >
        <Icon className="mr-2 h-3.5 w-3.5" />
        {actionLabel}
      </Button>
    </div>
  );
}
