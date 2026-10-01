"""Resolver-time belief freshness / decay (Phase 3D).

A belief's *stored* confidence records how strong the evidence was WHEN it was
established. But evidence goes stale: a channel insight from eight months ago is
weaker today even if nothing has contradicted it. This module computes an
``effective_confidence`` at read time from the stored confidence plus the
belief's age — WITHOUT ever mutating the stored value or the historical chain.

Guarantees (all pinned by tests):

* **Deterministic** — a pure function of (original confidence, reference time,
  now); no randomness, no I/O, no LLM.
* **Bounded** — the result is always in ``[floor, original]`` and never exceeds
  the stored confidence (freshness only *lowers*, never invents certainty).
* **Never negative** and ``0 -> 0`` — an unvalidated / insufficient-evidence
  belief (confidence 0) can never be aged *up* into something that looks held.
* **Monotonic with age** — older ⇒ effective confidence is ≤ that of a younger
  but otherwise identical belief.
* **Explainable** — returns a plain-language reason describing the decay band.
* **Non-destructive** — callers use the returned value for display / reasoning;
  the belief row's ``confidence`` is untouched, so history stays auditable.

Decay is a simple, explainable three-band curve: a *fresh* window with no
decay, a linear ramp, then a *stale* floor. No exponential magic — a founder
(and a test) can reason about it exactly.
"""

from __future__ import annotations

from datetime import UTC, datetime

# Tunables — explainable, not magic.
_FRESH_DAYS = 21  # within ~3 weeks a measured belief is treated as current
_STALE_DAYS = 180  # by ~6 months it has decayed to the floor
_MAX_DECAY = 0.60  # a belief never loses more than 60% of its confidence to age
_SPAN = _STALE_DAYS - _FRESH_DAYS


def _age_days(reference_time: datetime | None, now: datetime) -> int:
    """Whole days between ``reference_time`` and ``now`` (never negative).

    A missing or future reference time is treated as age 0 (fully fresh) so a
    belief is never penalized for a clock skew or a not-yet-validated timestamp.
    """
    if reference_time is None:
        return 0
    ref = reference_time if reference_time.tzinfo else reference_time.replace(tzinfo=UTC)
    now = now if now.tzinfo else now.replace(tzinfo=UTC)
    delta = now - ref
    return max(0, delta.days)


def _floor_value(original: int) -> int:
    return round(original * (1.0 - _MAX_DECAY))


def effective_confidence(
    *, original_confidence: int, reference_time: datetime | None, now: datetime | None = None
) -> tuple[int, str]:
    """Return (effective_confidence, human reason) for a belief's age.

    ``reference_time`` should be the belief's ``validated_at`` (when it last
    gained supporting evidence), falling back to ``valid_from``. ``original``
    is the stored, evidence-derived confidence and is treated as the hard
    ceiling — the result never exceeds it and never drops below the floor.
    """
    now = now or datetime.now(UTC)
    original = max(0, min(int(original_confidence), 100))
    if original <= 0:
        # Insufficient / unvalidated: no confidence to age, and never invent any.
        return 0, "No established confidence to age (unvalidated)."

    age = _age_days(reference_time, now)
    if age <= _FRESH_DAYS:
        decay_frac = 0.0
        band = f"fresh (≤{_FRESH_DAYS}d old)"
    elif age >= _STALE_DAYS:
        decay_frac = _MAX_DECAY
        band = f"stale (≥{_STALE_DAYS}d old)"
    else:
        decay_frac = _MAX_DECAY * (age - _FRESH_DAYS) / _SPAN
        band = f"aging ({age}d old)"

    floor = _floor_value(original)
    value = round(original * (1.0 - decay_frac))
    value = max(floor, min(value, original))
    value = max(0, value)

    if value == original:
        reason = f"Current — evidence is {band}; confidence held at {value}%."
    else:
        reason = (
            f"Aged down from {original}% to {value}% — evidence is {band}; "
            f"freshness lowers confidence but never the stored evidence."
        )
    return value, reason


def is_expired(valid_until: datetime | None, now: datetime | None = None) -> bool:
    """True if the belief's validity window has closed (``valid_until`` in the
    past). An expired belief is excluded from the *active* set but stays
    retrievable as history."""
    if valid_until is None:
        return False
    now = now or datetime.now(UTC)
    vu = valid_until if valid_until.tzinfo else valid_until.replace(tzinfo=UTC)
    now = now if now.tzinfo else now.replace(tzinfo=UTC)
    return vu <= now
