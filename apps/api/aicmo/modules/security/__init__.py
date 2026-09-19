"""Session inventory + security event audit trail.

Authentication is first-party (see `aicmo.auth`). This module owns:
  - the Active Sessions view over the first-party `user_sessions` store
    (so the founder can see + revoke devices)
  - the append-only audit log of security-relevant events

Public surfaces — all authenticated (/api/v1/security/...):
    GET    /sessions                — list my active first-party sessions
    POST   /sessions/{id}/revoke    — revoke one session (current is refused;
                                      use sign-out for it)
    POST   /sessions/revoke-all     — revoke every session except the current
    GET    /events                  — paginated audit timeline
    POST   /events                  — internal recorder for client-witnessed
                                      events (MFA challenge, failed login)
    GET    /summary                 — quick stats for the Security page
"""

from aicmo.modules.security.router import public_router, router

__all__ = ["router", "public_router"]
