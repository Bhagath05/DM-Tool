"""Phase 10.2c — Session inventory + security event audit trail.

Clerk owns authentication. This module owns:
  - the mirror of active Clerk sessions (so the founder can see + revoke devices)
  - the append-only audit log of security-relevant events
  - the Clerk webhook receiver that keeps the mirror fresh

Public surfaces:
  Authenticated (/api/v1/security/...):
    GET    /sessions                — list my active+recent sessions
    POST   /sessions/{id}/revoke    — revoke one session (calls Clerk admin API)
    POST   /sessions/revoke-all     — revoke every session except current
    GET    /events                  — paginated audit timeline
    POST   /events                  — internal recorder for events Clerk
                                      webhooks don't deliver (MFA challenge,
                                      failed login on signed-in routes)
    GET    /summary                 — quick stats for the Security page

  Public (/api/v1/webhooks/clerk):
    POST   /webhooks/clerk          — Svix-signature-verified webhook receiver
"""

from aicmo.modules.security.router import public_router, router

__all__ = ["router", "public_router"]
