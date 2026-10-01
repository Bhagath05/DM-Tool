"""Approval state machine for agent consequential actions.

Explicit states and a server-enforced transition table. There is no path from a
terminal/blocked state to execution: a rejected or expired approval can never
become EXECUTED, and an executed/failed approval is final.
"""

from __future__ import annotations

import enum


class ApprovalStatus(enum.StrEnum):
    PENDING = "pending"  # proposed; awaiting a human decision
    APPROVED = "approved"  # a human approved the EXACT action; not yet run
    REJECTED = "rejected"  # a human rejected it (terminal)
    EXPIRED = "expired"  # TTL elapsed before a decision/execution (terminal)
    EXECUTED = "executed"  # ran successfully (terminal)
    FAILED = "failed"  # ran but the execution failed (terminal)


# The ONLY permitted transitions. Anything not listed is rejected by the service.
ALLOWED_TRANSITIONS: dict[ApprovalStatus, frozenset[ApprovalStatus]] = {
    ApprovalStatus.PENDING: frozenset(
        {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED}
    ),
    ApprovalStatus.APPROVED: frozenset(
        {ApprovalStatus.EXECUTED, ApprovalStatus.FAILED, ApprovalStatus.EXPIRED}
    ),
    ApprovalStatus.REJECTED: frozenset(),
    ApprovalStatus.EXPIRED: frozenset(),
    ApprovalStatus.EXECUTED: frozenset(),
    ApprovalStatus.FAILED: frozenset(),
}

TERMINAL: frozenset[ApprovalStatus] = frozenset(
    {
        ApprovalStatus.REJECTED,
        ApprovalStatus.EXPIRED,
        ApprovalStatus.EXECUTED,
        ApprovalStatus.FAILED,
    }
)


def can_transition(current: ApprovalStatus, target: ApprovalStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())
