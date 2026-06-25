"""Organizations — top-level tenant.

An organization owns billing, team, and (transitively) every brand. Every
business row in the system carries `organization_id` for org-level
operations (usage rollups, audit scoping) and `brand_id` for the actual
data scope.

Member ↔ role is N:N. In Tier 1 each member holds exactly one role, but
the schema is designed for stacked roles ('Editor' + 'Publisher' on the
same person) without future migration.
"""
