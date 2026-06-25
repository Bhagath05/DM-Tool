"""Phase 10.2a — Connection state machine tests.

The legal transition graph is small and human-readable; pin it
exhaustively so an "I'll just allow this one" patch can't slip
through code review.
"""

from __future__ import annotations

import pytest

from aicmo.modules.integrations.schemas import ConnectionState
from aicmo.modules.integrations.state import (
    InvalidStateTransition,
    assert_transition,
    can_transition,
    legal_targets,
)

ALL_STATES: list[ConnectionState] = [
    "DISCONNECTED",
    "PENDING_AUTH",
    "ACTIVE",
    "EXPIRED",
    "ERROR",
    "SUSPENDED",
]

LEGAL_PAIRS: list[tuple[ConnectionState, ConnectionState]] = [
    ("DISCONNECTED", "PENDING_AUTH"),
    ("PENDING_AUTH", "ACTIVE"),
    ("PENDING_AUTH", "DISCONNECTED"),
    ("PENDING_AUTH", "ERROR"),
    ("ACTIVE", "EXPIRED"),
    ("ACTIVE", "ERROR"),
    ("ACTIVE", "SUSPENDED"),
    ("ACTIVE", "DISCONNECTED"),
    ("EXPIRED", "ACTIVE"),
    ("EXPIRED", "PENDING_AUTH"),
    ("EXPIRED", "DISCONNECTED"),
    ("ERROR", "ACTIVE"),
    ("ERROR", "PENDING_AUTH"),
    ("ERROR", "DISCONNECTED"),
    ("SUSPENDED", "ACTIVE"),
    ("SUSPENDED", "DISCONNECTED"),
]


@pytest.mark.parametrize("current,target", LEGAL_PAIRS)
def test_legal_transitions(
    current: ConnectionState, target: ConnectionState
) -> None:
    assert can_transition(current, target) is True
    assert_transition(current, target)  # must not raise
    assert target in legal_targets(current)


def test_every_other_pair_is_illegal() -> None:
    """Exhaustive check: anything not in LEGAL_PAIRS must be rejected,
    including self-transitions."""
    legal = set(LEGAL_PAIRS)
    for current in ALL_STATES:
        for target in ALL_STATES:
            if (current, target) in legal:
                continue
            assert can_transition(current, target) is False, (
                f"unexpected legal transition: {current} -> {target}"
            )
            with pytest.raises(InvalidStateTransition):
                assert_transition(current, target)


@pytest.mark.parametrize("state", ALL_STATES)
def test_self_transition_always_rejected(state: ConnectionState) -> None:
    """Re-entering the same state always means a bug somewhere upstream."""
    assert can_transition(state, state) is False


def test_invalid_state_transition_carries_from_to() -> None:
    """The exception is rich enough that the router can build a 409
    response from it."""
    try:
        assert_transition("DISCONNECTED", "ACTIVE")
    except InvalidStateTransition as exc:
        assert exc.current == "DISCONNECTED"
        assert exc.target == "ACTIVE"
        assert "DISCONNECTED" in str(exc) and "ACTIVE" in str(exc)
    else:
        pytest.fail("expected InvalidStateTransition")
