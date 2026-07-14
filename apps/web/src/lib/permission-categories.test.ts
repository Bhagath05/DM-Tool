import { describe, expect, it } from "vitest";

import {
  categoryMeta,
  groupPermissions,
  type PermissionLike,
} from "./permission-categories";

const P = (slug: string, category: string): PermissionLike => ({
  slug,
  category,
});

describe("categoryMeta", () => {
  it("maps known catalog categories to friendly labels", () => {
    expect(categoryMeta("crm").label).toBe("CRM");
    expect(categoryMeta("content").label).toBe("Creative Studio");
    expect(categoryMeta("organization").label).toBe("Administration");
  });

  it("falls back to a title-cased label for unknown categories", () => {
    const meta = categoryMeta("brand_new_thing");
    expect(meta.label).toBe("Brand New Thing");
    expect(meta.order).toBe(50); // sorts to the end
  });
});

describe("groupPermissions", () => {
  it("groups by category and orders Workspace before Administration", () => {
    const groups = groupPermissions([
      P("team.manage", "organization"),
      P("brand.manage", "brand"),
      P("crm.view", "crm"),
    ]);
    expect(groups.map((g) => g.label)).toEqual([
      "Workspace",
      "CRM",
      "Administration",
    ]);
  });

  it("only surfaces categories that actually have permissions", () => {
    const groups = groupPermissions([P("analytics.view", "analytics")]);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("Analytics");
    expect(groups[0].permissions).toHaveLength(1);
  });

  it("keeps every permission (nothing dropped)", () => {
    const perms = [
      P("campaign.create", "campaign"),
      P("campaign.edit", "campaign"),
      P("lead.view", "lead"),
    ];
    const total = groupPermissions(perms).reduce(
      (n, g) => n + g.permissions.length,
      0,
    );
    expect(total).toBe(3);
  });

  it("returns nothing for an empty catalog", () => {
    expect(groupPermissions([])).toEqual([]);
  });
});
