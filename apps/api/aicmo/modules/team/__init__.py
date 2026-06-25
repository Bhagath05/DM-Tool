"""Phase 10.2d — Team management.

What this module owns:
  - The `organization_invite` table + lifecycle (create/list/revoke/accept).
  - The canonical 4-role catalog (owner, admin, analyst, viewer) that
    the Settings → Team page UI renders from.
  - The aggregated team-overview endpoint that returns members +
    pending invites + the role catalog in one shot, so the page can
    render with a single API call.

What this module DOESN'T own (and why):
  - `members`, `member_roles`, role assignment / removal — those live
    in `aicmo/modules/orgs/` and are reused as-is. This module is the
    invite + overview layer on top.
  - Email delivery — there is no email integration in Phase 10.2.
    Invite URLs are generated and returned to the caller; how they
    reach the invitee (copy-paste / external email / Slack) is the
    caller's problem.
"""

from aicmo.modules.team.router import public_router, router

__all__ = ["router", "public_router"]
