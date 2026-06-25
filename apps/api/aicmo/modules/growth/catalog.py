"""The outcome taxonomy in code (industry-FREE — Law 2).

These mirror the `objective_kind` seed in migration 0035. They exist in code
so the no-industry-hardcoding guard (CS1-7) and offline callers have a
canonical, *outcome*-keyed reference. There is deliberately NO industry
dimension here — only business outcomes. The DB row is the source of truth
at runtime; this is the contract.
"""

from __future__ import annotations

# Outcome categories — what the business wants to happen. Never an industry.
OBJECTIVE_CATEGORIES: frozenset[str] = frozenset(
    {"lead", "booking", "sale", "awareness", "install", "hire", "signup", "traffic", "retention"}
)

# The seeded objective_kind slugs (outcome verbs).
OBJECTIVE_KIND_SLUGS: tuple[str, ...] = (
    "get_leads", "get_bookings", "drive_sales", "grow_awareness",
    "drive_installs", "hire", "get_signups", "drive_traffic", "retain_customers",
)
