"""P1 hardening — index every foreign-key column lacking one.

44 FK columns had no supporting index (audit finding), causing slow joins,
slow cascade-deletes, and lock escalation at scale. This adds a btree index
on each. Built CONCURRENTLY (in an autocommit block) so applying it on a live
production database does not lock writes.

Revision ID: 0044_fk_indexes
Revises: 0043_publishing_pipeline
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0044_fk_indexes"
down_revision: Union[str, None] = "0043_publishing_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) — every FK column without a leading-column index.
_FK_INDEXES: list[tuple[str, str]] = [
    ("advisor_recommendations", "organization_id"),
    ("ai_audit_events", "brand_id"),
    ("billing_upgrade_request", "current_plan_slug"),
    ("billing_upgrade_request", "requested_by_user_id"),
    ("billing_upgrade_request", "requested_plan_slug"),
    ("brands", "created_by_user_id"),
    ("campaign_plans", "objective_id"),
    ("campaign_plans", "trend_report_id"),
    ("connector_sync_runs", "connection_id"),
    ("content_assets", "organization_id"),
    ("creative_cost_event", "creative_project_id"),
    ("creative_design", "creative_project_id"),
    ("creative_design", "format_slug"),
    ("creative_export", "creative_asset_id"),
    ("creative_project", "campaign_id"),
    ("creative_project", "format_slug"),
    ("creative_results", "organization_id"),
    ("creative_variant", "creative_asset_id"),
    ("creative_variant", "creative_project_id"),
    ("generated_ads", "trend_report_id"),
    ("generated_content", "trend_report_id"),
    ("generated_visuals", "trend_report_id"),
    ("growth_objective", "objective_kind"),
    ("integration_connection", "brand_id"),
    ("integration_connection", "created_by_user_id"),
    ("invoice", "subscription_id"),
    ("member_roles", "assigned_by_user_id"),
    ("notification_preference", "organization_id"),
    ("organization_invite", "accepted_by_user_id"),
    ("organization_invite", "invited_by_user_id"),
    ("organization_invite", "revoked_by_user_id"),
    ("organization_members", "invited_by_user_id"),
    ("organization_members", "last_active_brand_id"),
    ("performance_diagnostics", "organization_id"),
    ("performance_events", "organization_id"),
    ("scheduled_posts", "content_asset_id"),
    ("scheduled_posts", "organization_id"),
    ("scheduled_posts", "recommendation_id"),
    ("scheduled_posts", "social_asset_id"),
    ("stripe_event", "organization_id"),
    ("subscription", "plan_slug"),
    ("usage_event", "brand_id"),
    ("usage_event", "user_id"),
    ("video_render", "video_scene_id"),
]


def _ix(tbl: str, col: str) -> str:
    return f"ix_{tbl}_{col}"


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction → autocommit block.
    with op.get_context().autocommit_block():
        for tbl, col in _FK_INDEXES:
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {_ix(tbl, col)} '
                f'ON "{tbl}" ("{col}")'
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for tbl, col in _FK_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_ix(tbl, col)}")
