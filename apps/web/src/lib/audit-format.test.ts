import { describe, expect, it } from "vitest";

import type { AuditEvent } from "@/lib/api";
import {
  actionCategory,
  actionLabel,
  actorLabel,
  auditToCsv,
} from "./audit-format";

const evt = (over: Partial<AuditEvent> = {}): AuditEvent => ({
  id: "e1",
  action: "role.created",
  actor_user_id: "u1",
  actor_email: "admin@acme.com",
  actor_name: "Ada Admin",
  target_type: "role",
  target_id: "r1",
  brand_id: null,
  before: null,
  after: null,
  occurred_at: "2026-07-14T10:00:00.000Z",
  ...over,
});

describe("actionLabel / actionCategory", () => {
  it("maps known actions to friendly labels + categories", () => {
    expect(actionLabel("member.invited")).toBe("User invited");
    expect(actionCategory("member.invited")).toBe("Invitations");
    expect(actionCategory("role.updated")).toBe("Roles");
    expect(actionCategory("member.deactivated")).toBe("Members");
  });
  it("falls back to title-case + Other for unknown actions", () => {
    expect(actionLabel("widget.frobnicated")).toBe("Widget Frobnicated");
    expect(actionCategory("widget.frobnicated")).toBe("Other");
  });
});

describe("actorLabel", () => {
  it("prefers name, then email, then System", () => {
    expect(actorLabel(evt())).toBe("Ada Admin");
    expect(actorLabel(evt({ actor_name: null }))).toBe("admin@acme.com");
    expect(actorLabel(evt({ actor_name: null, actor_email: null }))).toBe(
      "System",
    );
  });
});

describe("auditToCsv", () => {
  it("emits a header + one row per event", () => {
    const csv = auditToCsv([evt(), evt({ id: "e2", action: "role.deleted" })]);
    const lines = csv.split("\n");
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe("When,Action,Category,Actor,Actor email,Target");
    expect(lines[1]).toContain("Role created");
    expect(lines[2]).toContain("Role deleted");
  });
  it("escapes commas and quotes per RFC 4180", () => {
    const csv = auditToCsv([
      evt({ actor_name: 'Smith, "Bob"', actor_email: "b@x.com" }),
    ]);
    // Field with comma + quotes must be wrapped and quotes doubled.
    expect(csv).toContain('"Smith, ""Bob"""');
  });
  it("handles an empty list (header only)", () => {
    expect(auditToCsv([])).toBe(
      "When,Action,Category,Actor,Actor email,Target",
    );
  });
});
