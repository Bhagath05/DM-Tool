"use client";

/**
 * Create / duplicate a custom role.
 *
 * Create → POST /orgs/{id}/roles with name + slug + color + priority
 * (permissions are configured immediately after in the editor).
 * Duplicate → POST /orgs/{id}/roles/{id}/duplicate, which clones the
 * source role's ALLOW + DENY grants server-side.
 */

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Modal } from "@/components/ui/modal";
import { Textarea } from "@/components/ui/textarea";
import { api, type RbacRole } from "@/lib/api";
import { slugifyRoleName } from "@/lib/roles";
import { cn } from "@/lib/utils";

export const ROLE_COLORS = [
  "#6366f1",
  "#8b5cf6",
  "#a855f7",
  "#ec4899",
  "#ef4444",
  "#f97316",
  "#f59e0b",
  "#22c55e",
  "#14b8a6",
  "#0ea5e9",
  "#64748b",
  "#94a3b8",
];

interface Props {
  open: boolean;
  orgId: string;
  mode: "create" | "duplicate";
  source?: RbacRole | null;
  onClose: () => void;
  onCreated: (role: RbacRole) => void;
}

export function RoleFormDialog({
  open,
  orgId,
  mode,
  source,
  onClose,
  onCreated,
}: Props) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [description, setDescription] = useState("");
  const [color, setColor] = useState(ROLE_COLORS[0]);
  const [priority, setPriority] = useState(20);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Seed the form when opened.
  useEffect(() => {
    if (!open) return;
    const seedName =
      mode === "duplicate" && source ? `${source.name} copy` : "";
    setName(seedName);
    setSlug(slugifyRoleName(seedName));
    setSlugTouched(false);
    setDescription("");
    setColor(source?.color ?? ROLE_COLORS[0]);
    setPriority(source?.priority ?? 20);
    setError(null);
  }, [open, mode, source]);

  const onName = (v: string) => {
    setName(v);
    if (!slugTouched) setSlug(slugifyRoleName(v));
  };

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const role =
        mode === "duplicate" && source
          ? await api.rbac.duplicateRole(orgId, source.id, { slug, name })
          : await api.rbac.createRole(orgId, {
              slug,
              name,
              description: description || null,
              color,
              priority,
            });
      onCreated(role);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "We couldn't save this role.",
      );
    } finally {
      setSaving(false);
    }
  };

  const valid = name.trim().length > 0 && /^[a-z][a-z0-9_]{2,63}$/.test(slug);

  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title={mode === "duplicate" ? "Duplicate role" : "Create role"}
      description={
        mode === "duplicate"
          ? "Clones this role's permissions into a new custom role you can edit."
          : "New custom roles start empty — set permissions in the editor next."
      }
      data-testid="role-form-dialog"
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="role-name">Role name</Label>
          <Input
            id="role-name"
            value={name}
            onChange={(e) => onName(e.target.value)}
            placeholder="e.g. Growth Lead"
            autoFocus
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="role-slug">Identifier</Label>
          <Input
            id="role-slug"
            value={slug}
            onChange={(e) => {
              setSlugTouched(true);
              setSlug(e.target.value.toLowerCase());
            }}
            placeholder="growth_lead"
            aria-describedby="role-slug-hint"
          />
          <p id="role-slug-hint" className="text-xs text-muted-foreground">
            Lowercase letters, numbers, underscores. Used internally and can't
            match a system role.
          </p>
        </div>

        {mode === "create" && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="role-desc">Description</Label>
            <Textarea
              id="role-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What is this role for?"
              rows={2}
            />
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <Label>Color</Label>
          <div className="flex flex-wrap gap-2">
            {ROLE_COLORS.map((c) => (
              <button
                key={c}
                type="button"
                aria-label={`Color ${c}`}
                aria-pressed={color === c}
                onClick={() => setColor(c)}
                className={cn(
                  "h-6 w-6 rounded-full ring-offset-2 ring-offset-background transition",
                  color === c && "ring-2 ring-foreground",
                )}
                style={{ backgroundColor: c }}
              />
            ))}
          </div>
        </div>

        {error && (
          <p className="rounded-md bg-bad-soft px-3 py-2 text-xs text-bad-soft-foreground">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!valid || saving}>
            {saving
              ? "Saving…"
              : mode === "duplicate"
                ? "Duplicate"
                : "Create role"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
