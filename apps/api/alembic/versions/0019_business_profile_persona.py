"""business_profile persona segmentation

Revision ID: 0019_business_profile_persona
Revises: 0018_audit_events
Create Date: 2026-06-01

Adds a single nullable column `persona` to `business_profiles` for
segmentation (NOT authorization — those are in `roles` / `member_roles`).

Persona = what kind of business / role-in-business the user is:
  solo_founder, in_house_marketer, agency, freelancer, consultant, other

Used for personalising onboarding tutorial copy, dashboard headlines,
and which features get surfaced first. Nullable so existing profiles
created before this migration continue to work — downstream code reads
it as an optional hint, never a required gate.

CHECK constraint enforces the enum on the DB side. Pydantic enforces it
on the API side. Belt-and-braces because business analysts will write
direct SQL backfills later and we want them to fail fast on typos.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0019_business_profile_persona"
down_revision: Union[str, None] = "0018_audit_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Keep this list in sync with:
#   apps/api/aicmo/modules/onboarding/schemas.py — Persona Literal
#   apps/web/src/components/onboarding-wizard.tsx — PERSONAS constant
_ALLOWED = (
    "solo_founder",
    "in_house_marketer",
    "agency",
    "freelancer",
    "consultant",
    "other",
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE business_profiles "
        "ADD COLUMN persona VARCHAR(32) NULL"
    )
    # CHECK enforces the enum but stays NULL-tolerant so old rows pass.
    quoted = ", ".join(f"'{p}'" for p in _ALLOWED)
    op.execute(
        "ALTER TABLE business_profiles "
        f"ADD CONSTRAINT ck_business_profiles_persona "
        f"CHECK (persona IS NULL OR persona IN ({quoted}))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE business_profiles "
        "DROP CONSTRAINT IF EXISTS ck_business_profiles_persona"
    )
    op.execute("ALTER TABLE business_profiles DROP COLUMN IF EXISTS persona")
