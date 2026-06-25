"""performance intelligence — phase 9.1

Revision ID: 0020_performance_intelligence
Revises: 0019_business_profile_persona
Create Date: 2026-06-03

Phase 9.1 — Performance Intelligence Engine, CSV-only wedge.

This migration is intentionally additive only. Two concerns:

  1. CREATIVE TAGGING (mandatory, per design)
     Add seven nullable tag columns to the three existing creative
     tables — generated_visuals, generated_content, generated_ads.
     Every new generation will populate them; existing rows stay NULL
     and are backward-compatible (the performance engine treats NULL
     tags as "untagged" and excludes them from tag-based rollups
     rather than erroring).

       concept_family   - short slug, e.g. "transformation"
       emotion          - short slug, e.g. "warmth"
       audience         - short slug, e.g. "parents_25_45"
       funnel_stage     - awareness | consideration | conversion | retention
       business_goal    - short slug, e.g. "more_bookings"
       offer_type       - discount | free_trial | consultation | bundle | promotion | none
       platform         - already exists on the tables; we leave it alone

  2. PERFORMANCE STORE (new, isolated)
     Three new tables that no existing query touches:
       - performance_events:   raw rows from CSV upload (one per ad/day)
       - creative_results:     per-creative rollup cube (computed)
       - performance_diagnostics: Constitution-shaped diagnoses + actions

Every table inherits the tenant convention: organization_id + brand_id
(NOT NULL) with composite indexes on (brand_id, ...) for the hot read path.

Rollback strategy: drop the three new tables; the tag columns stay
because they're NULL-tolerant and removing them would invalidate any
new rows written between deploy and rollback. Downgrade restores the
pre-migration shape entirely (drops both the new tables AND the new
columns) on the assumption that we have no committed data yet.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0020_performance_intelligence"
down_revision: Union[str, None] = "0019_business_profile_persona"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------
# Enum allow-lists — kept in lock-step with:
#   apps/api/aicmo/modules/performance/schemas.py
#   apps/web/src/lib/performance-translator.ts
# ---------------------------------------------------------------------

_FUNNEL_STAGES = ("awareness", "consideration", "conversion", "retention")
_OFFER_TYPES = (
    "discount",
    "free_trial",
    "consultation",
    "bundle",
    "promotion",
    "seasonal",
    "none",
)
_DIAGNOSTIC_KINDS = ("winner", "loser", "fatigue", "audience_shift", "budget_reallocation")
_DIAGNOSTIC_STATUSES = ("open", "acted_on", "dismissed", "expired")
_TAGGED_TABLES = ("generated_visuals", "generated_content", "generated_ads")


def _check(name: str, values: Sequence[str], col: str) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return (
        f"ADD CONSTRAINT {name} "
        f"CHECK ({col} IS NULL OR {col} IN ({quoted}))"
    )


def upgrade() -> None:
    # -----------------------------------------------------------------
    # 1. CREATIVE TAGGING — additive columns on the three creative tables
    # -----------------------------------------------------------------
    for table in _TAGGED_TABLES:
        op.execute(
            f"ALTER TABLE {table} "
            "ADD COLUMN concept_family VARCHAR(64) NULL, "
            "ADD COLUMN emotion        VARCHAR(64) NULL, "
            "ADD COLUMN audience       VARCHAR(96) NULL, "
            "ADD COLUMN funnel_stage   VARCHAR(32) NULL, "
            "ADD COLUMN business_goal  VARCHAR(96) NULL, "
            "ADD COLUMN offer_type     VARCHAR(32) NULL"
        )
        op.execute(
            f"ALTER TABLE {table} "
            + _check(
                f"ck_{table}_funnel_stage", _FUNNEL_STAGES, "funnel_stage"
            )
        )
        op.execute(
            f"ALTER TABLE {table} "
            + _check(f"ck_{table}_offer_type", _OFFER_TYPES, "offer_type")
        )
        # Composite index on (brand_id, concept_family) — the hot path
        # for tag-aware rollups. We deliberately do NOT add per-tag
        # indexes; the engine reads through creative_results, not the
        # raw creative tables.
        op.execute(
            f"CREATE INDEX ix_{table}_brand_concept "
            f"ON {table} (brand_id, concept_family)"
        )

    # -----------------------------------------------------------------
    # 2. PERFORMANCE EVENTS — raw CSV row store
    #
    # One row per (creative, date). Money is stored in *_micros (BIGINT)
    # so we never round-trip to float. Currency is a 3-letter ISO code
    # captured from the upload; we never assume INR or USD.
    # -----------------------------------------------------------------
    op.create_table(
        "performance_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "upload_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Groups all rows ingested from one CSV upload.",
        ),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        # `creative_ref` is the upload's name for this ad. Free-text;
        # we attempt to fuzzy-match to our generated creatives at
        # rollup time but never block on a match.
        sa.Column("creative_ref", sa.String(255), nullable=False),
        # If we matched the ref to one of our generated creatives, this
        # gets the source table + id so the rollup can join tags.
        sa.Column(
            "matched_asset_type",
            sa.String(16),
            nullable=True,
            comment="visual | content | ad — NULL when no match.",
        ),
        sa.Column(
            "matched_asset_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "spend_micros",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="Spend × 1_000_000 in the row's currency. Never float.",
        ),
        sa.Column(
            "conversion_value_micros",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="Conversion value × 1_000_000. 0 when not provided.",
        ),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_performance_events_brand_date",
        "performance_events",
        ["brand_id", "event_date"],
    )
    op.create_index(
        "ix_performance_events_brand_creative",
        "performance_events",
        ["brand_id", "creative_ref"],
    )
    op.create_index(
        "ix_performance_events_upload",
        "performance_events",
        ["brand_id", "upload_id"],
    )

    # -----------------------------------------------------------------
    # 3. CREATIVE_RESULTS — rolled-up cube per creative
    #
    # Computed by service.recompute_rollups() after every ingest. Plain
    # table (not MV) — simpler ops; promote to MV only when reads suffer.
    # -----------------------------------------------------------------
    op.create_table(
        "creative_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("creative_ref", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("matched_asset_type", sa.String(16), nullable=True),
        sa.Column(
            "matched_asset_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        # Tag snapshot at rollup time — duplicated from the matched
        # asset row for query speed and so rollups survive if a tag
        # is later changed on the asset.
        sa.Column("concept_family", sa.String(64), nullable=True),
        sa.Column("emotion", sa.String(64), nullable=True),
        sa.Column("audience", sa.String(96), nullable=True),
        sa.Column("funnel_stage", sa.String(32), nullable=True),
        sa.Column("business_goal", sa.String(96), nullable=True),
        sa.Column("offer_type", sa.String(32), nullable=True),
        # Aggregated facts (over the brand's complete ingested window).
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "spend_micros", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "conversion_value_micros",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("first_seen", sa.Date(), nullable=False),
        sa.Column("last_seen", sa.Date(), nullable=False),
        # Pre-computed sample-state ("sufficient" iff min-thresholds met).
        # Saves the diagnostic engine from re-checking on every read.
        sa.Column(
            "sample_state",
            sa.String(16),
            nullable=False,
            server_default="insufficient",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_creative_results_brand_creative",
        "creative_results",
        ["brand_id", "creative_ref"],
        unique=True,
    )
    op.create_index(
        "ix_creative_results_brand_platform",
        "creative_results",
        ["brand_id", "platform"],
    )

    # -----------------------------------------------------------------
    # 4. PERFORMANCE_DIAGNOSTICS — Constitution-shaped diagnosis store
    #
    # One row per surfaced diagnosis. The Recommendation Composer
    # writes these; the dashboard reads them via the performance
    # router. Constitution-required fields are NOT NULL.
    # -----------------------------------------------------------------
    op.create_table(
        "performance_diagnostics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("impact_category", sa.String(16), nullable=False),
        sa.Column("what_happened", sa.Text(), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        "ALTER TABLE performance_diagnostics "
        + _check("ck_perf_diag_kind", _DIAGNOSTIC_KINDS, "kind")
    )
    op.execute(
        "ALTER TABLE performance_diagnostics "
        + _check("ck_perf_diag_status", _DIAGNOSTIC_STATUSES, "status")
    )
    op.execute(
        "ALTER TABLE performance_diagnostics "
        "ADD CONSTRAINT ck_perf_diag_confidence "
        "CHECK (confidence BETWEEN 0 AND 100)"
    )
    op.create_index(
        "ix_perf_diag_brand_status",
        "performance_diagnostics",
        ["brand_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_perf_diag_brand_status", table_name="performance_diagnostics")
    op.drop_table("performance_diagnostics")

    op.drop_index(
        "ix_creative_results_brand_platform", table_name="creative_results"
    )
    op.drop_index(
        "ix_creative_results_brand_creative", table_name="creative_results"
    )
    op.drop_table("creative_results")

    op.drop_index(
        "ix_performance_events_upload", table_name="performance_events"
    )
    op.drop_index(
        "ix_performance_events_brand_creative", table_name="performance_events"
    )
    op.drop_index(
        "ix_performance_events_brand_date", table_name="performance_events"
    )
    op.drop_table("performance_events")

    for table in _TAGGED_TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_brand_concept")
        op.execute(
            f"ALTER TABLE {table} "
            f"DROP CONSTRAINT IF EXISTS ck_{table}_funnel_stage, "
            f"DROP CONSTRAINT IF EXISTS ck_{table}_offer_type"
        )
        op.execute(
            f"ALTER TABLE {table} "
            "DROP COLUMN IF EXISTS concept_family, "
            "DROP COLUMN IF EXISTS emotion, "
            "DROP COLUMN IF EXISTS audience, "
            "DROP COLUMN IF EXISTS funnel_stage, "
            "DROP COLUMN IF EXISTS business_goal, "
            "DROP COLUMN IF EXISTS offer_type"
        )
