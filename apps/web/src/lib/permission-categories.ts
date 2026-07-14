/**
 * Phase 6.6 — permission category presentation.
 *
 * The permission catalog (GET /rbac/permissions) is the single source of
 * truth; each permission carries a `category` slug. This module only maps
 * those real categories to a friendly display label, an order, and an
 * icon so the editor can group them — it never invents permissions.
 *
 * Unknown categories (ones added to the catalog later, e.g. `ads`, `ai`,
 * `tasks`, `integrations`) fall back to a title-cased label and sort to
 * the end, so new permissions light up automatically without a code
 * change here. Pre-seeding a few forward-looking entries just gives them
 * a nicer label + icon the day their permissions land.
 */

import {
  BarChart3,
  Bot,
  Building2,
  CreditCard,
  FolderOpen,
  type LucideIcon,
  Megaphone,
  Palette,
  Plug,
  Send,
  Shield,
  Target,
  UserPlus,
  Users,
} from "lucide-react";

export interface CategoryMeta {
  label: string;
  order: number;
  icon: LucideIcon;
}

const CATEGORY_META: Record<string, CategoryMeta> = {
  // Present in the catalog today.
  brand: { label: "Workspace", order: 0, icon: Building2 },
  crm: { label: "CRM", order: 2, icon: Users },
  lead: { label: "Leads", order: 3, icon: UserPlus },
  campaign: { label: "Campaigns", order: 4, icon: Megaphone },
  content: { label: "Creative Studio", order: 5, icon: Palette },
  publish: { label: "Publishing", order: 6, icon: Send },
  analytics: { label: "Analytics", order: 7, icon: BarChart3 },
  library: { label: "Library", order: 8, icon: FolderOpen },
  billing: { label: "Billing", order: 9, icon: CreditCard },
  organization: { label: "Administration", order: 12, icon: Shield },
  // Forward-looking — no permissions yet, so these never render today,
  // but they're ready the moment the catalog gains them.
  ads: { label: "Ads", order: 4.5, icon: Target },
  ai: { label: "AI", order: 7.5, icon: Bot },
  integrations: { label: "Integrations", order: 11, icon: Plug },
};

function titleCase(slug: string): string {
  return slug.replace(/[_-]+/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

export function categoryMeta(category: string): CategoryMeta {
  return (
    CATEGORY_META[category] ?? {
      label: titleCase(category),
      order: 50,
      icon: Shield,
    }
  );
}

export interface PermissionLike {
  slug: string;
  category: string;
}

export interface PermissionGroup<T extends PermissionLike> {
  category: string;
  label: string;
  icon: LucideIcon;
  permissions: T[];
}

/**
 * Group a flat permission list into ordered, labelled categories. Only
 * categories that actually have permissions appear.
 */
export function groupPermissions<T extends PermissionLike>(
  permissions: T[],
): PermissionGroup<T>[] {
  const byCategory = new Map<string, T[]>();
  for (const p of permissions) {
    const list = byCategory.get(p.category) ?? [];
    list.push(p);
    byCategory.set(p.category, list);
  }
  return [...byCategory.entries()]
    .map(([category, perms]) => {
      const meta = categoryMeta(category);
      return {
        category,
        label: meta.label,
        icon: meta.icon,
        permissions: perms,
      };
    })
    .sort(
      (a, b) =>
        categoryMeta(a.category).order - categoryMeta(b.category).order ||
        a.label.localeCompare(b.label),
    );
}
