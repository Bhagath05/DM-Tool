"use client";

/**
 * Permissions tab — the tri-state (Allow / Deny / Inherit) matrix.
 *
 * Renders the REAL permission catalog grouped by category. Never
 * hardcodes permissions: everything comes from `permissions` (GET
 * /rbac/permissions). "Inherit" is the absence of an explicit grant and
 * resolves to whatever the member's other roles say — matching the
 * Slice 2 permission engine exactly.
 *
 * Controlled by the editor: it owns the draft allow/deny sets and this
 * component just reflects + edits them.
 */

import { Check, ChevronDown, Minus, Search, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Input } from "@/components/ui/input";
import type { RbacPermission } from "@/lib/api";
import { groupPermissions } from "@/lib/permission-categories";
import type { PermissionEffect } from "@/lib/roles";
import { cn } from "@/lib/utils";

interface Props {
  permissions: RbacPermission[];
  allow: Set<string>;
  deny: Set<string>;
  editable: boolean;
  onSet: (slug: string, effect: PermissionEffect) => void;
}

export function PermissionsTab({
  permissions,
  allow,
  deny,
  editable,
  onSet,
}: Props) {
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const groups = useMemo(() => groupPermissions(permissions), [permissions]);

  const q = query.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!q) return groups;
    return groups
      .map((g) => ({
        ...g,
        permissions: g.permissions.filter(
          (p) =>
            p.name.toLowerCase().includes(q) ||
            p.slug.toLowerCase().includes(q) ||
            g.label.toLowerCase().includes(q) ||
            (p.description ?? "").toLowerCase().includes(q),
        ),
      }))
      .filter((g) => g.permissions.length > 0);
  }, [groups, q]);

  const effectOf = (slug: string): PermissionEffect =>
    allow.has(slug) ? "allow" : deny.has(slug) ? "deny" : "inherit";

  const allCollapsed = collapsed.size === groups.length && groups.length > 0;

  return (
    <div className="flex flex-col gap-4" data-testid="permissions-tab">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative sm:max-w-xs sm:flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search permissions"
            className="pl-8"
            aria-label="Search permissions"
            data-testid="permission-search"
          />
        </div>
        <button
          type="button"
          onClick={() =>
            setCollapsed(
              allCollapsed
                ? new Set()
                : new Set(groups.map((g) => g.category)),
            )
          }
          className="self-start text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          {allCollapsed ? "Expand all" : "Collapse all"}
        </button>
      </div>

      {filtered.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No permissions match “{query}”.
        </p>
      )}

      <div className="flex flex-col gap-3">
        {filtered.map((group) => {
          const isCollapsed = collapsed.has(group.category) && !q;
          const GroupIcon = group.icon;
          const grantedInGroup = group.permissions.filter((p) =>
            allow.has(p.slug),
          ).length;
          return (
            <section
              key={group.category}
              className="overflow-hidden rounded-lg border border-border"
              data-testid={`permission-group-${group.category}`}
            >
              <button
                type="button"
                onClick={() =>
                  setCollapsed((prev) => {
                    const next = new Set(prev);
                    if (next.has(group.category)) next.delete(group.category);
                    else next.add(group.category);
                    return next;
                  })
                }
                className="flex w-full items-center gap-2.5 bg-muted/40 px-3 py-2.5 text-left hover:bg-muted/70"
                aria-expanded={!isCollapsed}
              >
                <GroupIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="text-sm font-semibold">{group.label}</span>
                <span className="text-xs text-muted-foreground">
                  {grantedInGroup}/{group.permissions.length} allowed
                </span>
                <ChevronDown
                  className={cn(
                    "ml-auto h-4 w-4 text-muted-foreground transition-transform",
                    isCollapsed && "-rotate-90",
                  )}
                />
              </button>

              {!isCollapsed && (
                <ul className="divide-y divide-border">
                  {group.permissions.map((perm) => (
                    <li
                      key={perm.slug}
                      className="flex items-center gap-3 px-3 py-2.5"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">
                          {perm.name}
                        </p>
                        {perm.description && (
                          <p className="truncate text-xs text-muted-foreground">
                            {perm.description}
                          </p>
                        )}
                      </div>
                      <TriToggle
                        value={effectOf(perm.slug)}
                        editable={editable}
                        onChange={(e) => onSet(perm.slug, e)}
                        label={perm.name}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

const OPTIONS: {
  value: PermissionEffect;
  label: string;
  icon: typeof Check;
  tone: string;
}[] = [
  { value: "inherit", label: "Inherit", icon: Minus, tone: "text-muted-foreground" },
  { value: "allow", label: "Allow", icon: Check, tone: "text-good" },
  { value: "deny", label: "Deny", icon: X, tone: "text-bad" },
];

function TriToggle({
  value,
  editable,
  onChange,
  label,
}: {
  value: PermissionEffect;
  editable: boolean;
  onChange: (e: PermissionEffect) => void;
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={`${label} permission`}
      className="inline-flex shrink-0 overflow-hidden rounded-md border border-border"
    >
      {OPTIONS.map((opt) => {
        const active = opt.value === value;
        const Icon = opt.icon;
        const activeCls =
          opt.value === "allow"
            ? "bg-good-soft text-good-soft-foreground"
            : opt.value === "deny"
              ? "bg-bad-soft text-bad-soft-foreground"
              : "bg-secondary text-foreground";
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={!editable}
            onClick={() => editable && onChange(opt.value)}
            title={opt.label}
            className={cn(
              "flex items-center gap-1 px-2 py-1 text-xs font-medium transition-colors",
              active
                ? activeCls
                : "text-muted-foreground hover:bg-muted disabled:hover:bg-transparent",
              !editable && "cursor-default opacity-90",
            )}
            data-testid={`tri-${opt.value}`}
          >
            <Icon className={cn("h-3.5 w-3.5", active && opt.tone)} />
            <span className="hidden sm:inline">{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
