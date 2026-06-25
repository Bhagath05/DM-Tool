"""extend performance_diagnostics.kind for phase 9.1.5

Revision ID: 0021_perf_intel_kinds
Revises: 0020_performance_intelligence
Create Date: 2026-06-03

Phase 9.1.5 — Performance Marketer Brain.

Adds 11 new diagnostic kinds to the existing CHECK constraint on
`performance_diagnostics.kind`. No new tables, no new columns —
the intelligence layers read the same `creative_results` cube.

New kinds (kept in lock-step with apps/api/aicmo/modules/performance/schemas.py
and apps/web/src/lib/api.ts):

  audience_winner            top-performing audience tag
  audience_loser             worst-performing audience tag
  concept_winner             top-performing concept_family tag
  emotion_winner             top-performing emotion tag
  funnel_winner              top-performing funnel_stage tag
  pattern_winner             best (concept_family × emotion) combo — hook proxy
  offer_winner               top-performing offer_type tag
  offer_pricing_sensitivity  discount vs no-discount comparison
  scale_candidate            creative that should get more spend
  budget_waste               creative that should lose spend
  creative_dna               apex card — best 5-tag combo (audience × concept ×
                             emotion × offer × funnel_stage)

The CHECK constraint is replaced atomically with the union of the 9.1
kinds and the new ones. Downgrade restores the 9.1-only set.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0021_perf_intel_kinds"
down_revision: Union[str, None] = "0020_performance_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Pre-9.1.5 set — kept here for the downgrade path.
_KINDS_0020 = (
    "winner",
    "loser",
    "fatigue",
    "audience_shift",
    "budget_reallocation",
)

# Post-9.1.5 set = 9.1 set + 11 new kinds (audience/creative/offer/
# scaling intelligence + creative_dna apex card).
_KINDS_0021 = _KINDS_0020 + (
    "audience_winner",
    "audience_loser",
    "concept_winner",
    "emotion_winner",
    "funnel_winner",
    "pattern_winner",
    "offer_winner",
    "offer_pricing_sensitivity",
    "scale_candidate",
    "budget_waste",
    "creative_dna",
)


def _check_sql(values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return (
        "ADD CONSTRAINT ck_perf_diag_kind "
        f"CHECK (kind IN ({quoted}))"
    )


def upgrade() -> None:
    # Drop and re-add atomically so we don't briefly accept any value.
    op.execute(
        "ALTER TABLE performance_diagnostics "
        "DROP CONSTRAINT IF EXISTS ck_perf_diag_kind"
    )
    op.execute(
        "ALTER TABLE performance_diagnostics " + _check_sql(_KINDS_0021)
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE performance_diagnostics "
        "DROP CONSTRAINT IF EXISTS ck_perf_diag_kind"
    )
    op.execute(
        "ALTER TABLE performance_diagnostics " + _check_sql(_KINDS_0020)
    )
