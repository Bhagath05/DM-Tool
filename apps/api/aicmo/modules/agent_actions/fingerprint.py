"""Deterministic action fingerprinting (Phase 4A).

An approval binds to the EXACT action, not a type of action. The fingerprint is
a stable hash over the canonical, server-validated representation of the action:
tenant + brand + tool + operation class + validated input. If any of these
changes after approval, the fingerprint changes and the old approval is invalid.

Crucially, we fingerprint the VALIDATED server-side input (a Pydantic dump with
sorted keys) — never raw LLM JSON. The model cannot influence the fingerprint
except through input that already passed the tool's schema.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def canonical_action(
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID | None,
    tool_name: str,
    operation_class: str,
    action_input: dict[str, Any],
) -> str:
    """A canonical, stable string for the action. Deterministic key order and
    JSON-safe value coercion so the same action always hashes identically."""
    payload = {
        "organization_id": str(organization_id),
        "brand_id": str(brand_id) if brand_id is not None else None,
        "tool_name": tool_name,
        "operation_class": operation_class,
        "input": action_input,
    }
    # default=str coerces UUID/datetime deterministically; sort_keys makes the
    # representation order-independent.
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint_action(
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID | None,
    tool_name: str,
    operation_class: str,
    action_input: dict[str, Any],
) -> str:
    canonical = canonical_action(
        organization_id=organization_id,
        brand_id=brand_id,
        tool_name=tool_name,
        operation_class=operation_class,
        action_input=action_input,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def idempotency_key(fingerprint: str) -> str:
    """Execution idempotency key derived from the approved action's fingerprint —
    never from client input. The same approved action yields the same key, so a
    retry can be recognized and de-duplicated."""
    return hashlib.sha256(f"exec:{fingerprint}".encode()).hexdigest()
