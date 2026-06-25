"""Pure-function state-machine for `IntegrationConnection.state`.

Every transition the service layer wants to make goes through
`assert_transition(current, next)` first. Invalid transitions raise
`InvalidStateTransition` — surfaced as 409 by the router.

Why a separate module: the legal transition graph is the kind of
thing reviewers and future-me need to be able to read in 30 seconds.
Keeping it out of the service file (which orchestrates DB writes +
provider calls) means the rule lives in one place and is trivially
unit-testable without touching the DB.

The transition table mirrors the diagram in the Phase 10.2 plan:

    DISCONNECTED ── connect() ──▶ PENDING_AUTH ── callback ok ──▶ ACTIVE
                                       │                            │
                                       │ callback fail              ├─ refresh fail ──▶ EXPIRED
                                       └──────────────────────────▶ DISCONNECTED
                                                                    │
                                                                    ├─ sync fail ─────▶ ERROR
                                                                    │
                                                                    └─ user pause ────▶ SUSPENDED

    Any non-DISCONNECTED state ──▶ DISCONNECTED  (user clicks disconnect)
    EXPIRED / ERROR / SUSPENDED ──▶ PENDING_AUTH (user reconnects / retries)
"""

from __future__ import annotations

from aicmo.modules.integrations.schemas import ConnectionState

# ---------------------------------------------------------------------
#  Legal transition table
# ---------------------------------------------------------------------

_LEGAL: dict[ConnectionState, set[ConnectionState]] = {
    "DISCONNECTED": {"PENDING_AUTH"},
    "PENDING_AUTH": {"ACTIVE", "DISCONNECTED", "ERROR"},
    "ACTIVE": {"EXPIRED", "ERROR", "SUSPENDED", "DISCONNECTED"},
    "EXPIRED": {"ACTIVE", "PENDING_AUTH", "DISCONNECTED"},
    "ERROR": {"ACTIVE", "PENDING_AUTH", "DISCONNECTED"},
    "SUSPENDED": {"ACTIVE", "DISCONNECTED"},
}


# ---------------------------------------------------------------------
#  Public surface
# ---------------------------------------------------------------------


class InvalidStateTransition(ValueError):
    """The state machine rejected this transition. Carries the from/to
    so the router can return a clean 409 with the founder-readable
    "this connection isn't in a state that supports X" message."""

    def __init__(self, current: ConnectionState, target: ConnectionState):
        self.current = current
        self.target = target
        super().__init__(
            f"Cannot transition connection from {current} to {target}."
        )


def can_transition(current: ConnectionState, target: ConnectionState) -> bool:
    """Pure predicate — useful for callers that want to short-circuit
    UI affordances without raising."""
    if current == target:
        return False  # no-op transitions are always rejected — the
        # service layer asks "is this a real change?" before persisting,
        # so re-entering the same state means something went wrong.
    return target in _LEGAL.get(current, set())


def assert_transition(
    current: ConnectionState, target: ConnectionState
) -> None:
    """Raise if `current → target` isn't in the legal table.
    Returns None on success — the service layer then performs the
    actual DB write."""
    if not can_transition(current, target):
        raise InvalidStateTransition(current, target)


def legal_targets(current: ConnectionState) -> set[ConnectionState]:
    """Reflective helper — what states can `current` go to? Used by
    the UI to enable/disable buttons (Phase 10.2g)."""
    return set(_LEGAL.get(current, set()))
