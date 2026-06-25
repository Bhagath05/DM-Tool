"""Coach module — Phase 2.2+.

Strategic / advisory layer that sits ALONGSIDE the generation modules
(content, ads, visuals, campaigns) without depending on or replacing them.

Current surfaces:
- reality: heuristic + AI feasibility check for user-stated goals.

Planned (later phases):
- weekly: composition layer over content + campaigns + analytics that
  answers "what should I do this week?"

The module never writes to user-owned tables. It is read-only against
the business profile and computes advisory output on demand.
"""
