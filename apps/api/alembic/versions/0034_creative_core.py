"""Creative Platform core + Video subsystem (V0) — dark-launch foundation

Revision ID: 0034_creative_core
Revises: 0033_billing_live
Create Date: 2026-06-11

Unified Creative Studio core (media-agnostic) + the Video subsystem's
video-specific tables. Per CREATIVE_PLATFORM_ARCHITECTURE_REVIEW.md, the
shared tables are named `creative_*` NOW (while empty) so future creative
types (posters/banners/carousels/...) drop in with no rename migration.

Creates:
  core (tenant): creative_project, creative_asset, creative_variant,
                 creative_cost_event, brand_kit, creative_template,
                 creative_export
  core (catalog): creative_format          (non-tenant, like `plan`)
  video subsystem: video_scene, video_render

Plus: indexes, dormant RLS policies on the 9 tenant tables, creative_format
seed (7 platforms), usage_event.kind += video_generation/video_second,
plan_quota seed for video_generation, RBAC video.* permissions + grants.

No video bytes here — renders/assets store a StorageRef
(storage_backend + storage_key). Additive + reversible. visuals/content
untouched.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from aicmo.db import rls


revision: str = "0034_creative_core"
down_revision: Union[str, None] = "0033_billing_live"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TENANT_TABLES = (
    "creative_project", "creative_asset", "creative_variant",
    "creative_cost_event", "brand_kit", "creative_template",
    "creative_export", "video_scene", "video_render",
)

_NEW_USAGE_KINDS = ("video_generation", "video_second")
_USAGE_KINDS_AFTER_0033 = (
    "csv_upload", "lead_processed", "ai_recommendation", "creative_analysis",
    "campaign_analysis", "generation", "campaign", "lead",
)

# (slug, display_name, media_type, platform, aspect, w, h, max_dur_s, fps, seeding, style)
_FORMATS = (
    ("instagram_reels", "Instagram Reels", "video", "instagram", "9:16", 1080, 1920, 60, 24, "optional", "hook_first_fast_cuts"),
    ("tiktok", "TikTok", "video", "tiktok", "9:16", 1080, 1920, 60, 24, "optional", "ugc_native_energy"),
    ("youtube_shorts", "YouTube Shorts", "video", "youtube", "9:16", 1080, 1920, 60, 24, "optional", "retention_loopable"),
    ("meta_ads", "Meta Ads", "video", "meta", "4:5", 1080, 1350, 15, 24, "optional", "offer_cta_card"),
    ("facebook_ads", "Facebook Ads", "video", "facebook", "1:1", 1080, 1080, 15, 24, "optional", "benefit_led_cta"),
    ("ugc_ad", "UGC Advertisement", "video", "multi", "9:16", 1080, 1920, 30, 24, "image_to_video", "handheld_authentic"),
    ("product_commercial", "Product Commercial", "video", "multi", "16:9", 1920, 1080, 30, 24, "image_to_video", "polished_studio"),
)

# (plan_slug, monthly_limit) for the video_generation quota. None = unlimited.
_VIDEO_QUOTAS = (("free", 2), ("starter", 30), ("growth", 300))

_PERMISSIONS = (
    ("video.create", "Create creative / video", "creative"),
    ("video.read", "View creative / video", "creative"),
    ("video.publish", "Publish creative", "creative"),
)
_GRANTS = (
    ("owner", "video.create"), ("admin", "video.create"), ("editor", "video.create"),
    ("owner", "video.read"), ("admin", "video.read"), ("editor", "video.read"),
    ("analyst", "video.read"), ("viewer", "video.read"),
    ("owner", "video.publish"), ("admin", "video.publish"),
)


def _uuid_pk():
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def _tenant_cols():
    return (
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True),
    )


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def upgrade() -> None:
    # ---- creative_format (catalog, non-tenant) ----
    op.create_table(
        "creative_format",
        sa.Column("slug", sa.String(48), primary_key=True),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("aspect_ratio", sa.String(8), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("max_duration_s", sa.Integer(), nullable=True),
        sa.Column("fps", sa.Integer(), nullable=True),
        sa.Column("seeding", sa.String(16), nullable=False, server_default="optional"),
        sa.Column("style_preset", sa.String(48), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.bulk_insert(
        sa.table(
            "creative_format",
            sa.column("slug"), sa.column("display_name"), sa.column("media_type"),
            sa.column("platform"), sa.column("aspect_ratio"), sa.column("width"),
            sa.column("height"), sa.column("max_duration_s"), sa.column("fps"),
            sa.column("seeding"), sa.column("style_preset"), sa.column("sort_order"),
        ),
        [
            {"slug": s, "display_name": n, "media_type": m, "platform": p,
             "aspect_ratio": a, "width": w, "height": h, "max_duration_s": d,
             "fps": f, "seeding": seed, "style_preset": st, "sort_order": i}
            for i, (s, n, m, p, a, w, h, d, f, seed, st) in enumerate(_FORMATS)
        ],
    )

    # ---- creative_project ----
    op.create_table(
        "creative_project",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("business_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("campaign_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("brief", sa.Text(), nullable=True),
        sa.Column("creative_type", sa.String(32), nullable=False),   # poster|banner|carousel|thumbnail|social_post|reel_cover|video
        sa.Column("media_type", sa.String(16), nullable=False),       # image|carousel|composite|video
        sa.Column("format_slug", sa.String(48),
                  sa.ForeignKey("creative_format.slug", ondelete="RESTRICT"), nullable=True),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column("objective", sa.String(64), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("tone", sa.String(64), nullable=True),
        sa.Column("audio_mode", sa.String(16), nullable=False, server_default="tts_voiceover"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("script", postgresql.JSONB(), nullable=True),
        sa.Column("seed_asset_ref", postgresql.JSONB(), nullable=True),   # image-to-video seed StorageRef
        sa.Column("spec", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ab_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("estimated_cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_cost_cents", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.create_index("ix_creative_project_brand_created", "creative_project",
                    ["brand_id", sa.text("created_at DESC")])

    # ---- creative_asset (the unified Asset Library row) ----
    op.create_table(
        "creative_asset",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("creative_project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("creative_project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_label", sa.String(16), nullable=True),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("creative_type", sa.String(32), nullable=False),
        # Polymorphic pointer to the native render row (no FK — source tables vary):
        sa.Column("source_kind", sa.String(32), nullable=True),       # video_render|rendered_visual|generated_content
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("storage_backend", sa.String(16), nullable=True),    # local|s3
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("poster_storage_key", sa.String(512), nullable=True),
        sa.Column("caption_storage_key", sa.String(512), nullable=True),
        sa.Column("mime_type", sa.String(48), nullable=True),
        sa.Column("aspect_ratio", sa.String(8), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="assembling"),
        sa.Column("published_ref", postgresql.JSONB(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_creative_asset_brand_created", "creative_asset",
                    ["brand_id", sa.text("created_at DESC")])
    op.create_index("ix_creative_asset_project", "creative_asset", ["creative_project_id"])

    # ---- creative_variant ----
    op.create_table(
        "creative_variant",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("creative_project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("creative_project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ab_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("creative_asset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("creative_asset.id", ondelete="SET NULL"), nullable=True),
        sa.Column("variant_label", sa.String(16), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column("variable_changed", sa.String(32), nullable=True),
        sa.Column("is_control", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("performance", postgresql.JSONB(), nullable=True),
        *_timestamps(),
    )

    # ---- creative_cost_event (cost ledger — append-only) ----
    op.create_table(
        "creative_cost_event",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("creative_project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("creative_project.id", ondelete="SET NULL"), nullable=True),
        sa.Column("media_type", sa.String(16), nullable=True),
        sa.Column("stage", sa.String(32), nullable=False),           # veo_clip|tts|asr|image_seed|storage
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("units", sa.Numeric(12, 3), nullable=False, server_default="0"),
        sa.Column("unit_cost_cents", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_creative_cost_org_time", "creative_cost_event",
                    ["organization_id", sa.text("occurred_at DESC")])

    # ---- brand_kit ----
    op.create_table(
        "brand_kit",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("logo_storage_key", sa.String(512), nullable=True),
        sa.Column("watermark_position", sa.String(16), nullable=True),
        sa.Column("color_primary", sa.String(16), nullable=True),
        sa.Column("color_secondary", sa.String(16), nullable=True),
        sa.Column("color_accent", sa.String(16), nullable=True),
        sa.Column("font_heading", sa.String(64), nullable=True),
        sa.Column("font_body", sa.String(64), nullable=True),
        sa.Column("intro_template_key", sa.String(512), nullable=True),
        sa.Column("outro_template_key", sa.String(512), nullable=True),
        sa.Column("end_card_cta", sa.Text(), nullable=True),
        sa.Column("voice_provider", sa.String(32), nullable=True),
        sa.Column("voice_id", sa.String(128), nullable=True),
        sa.Column("music_mood", sa.String(64), nullable=True),
        sa.Column("safe_zones", postgresql.JSONB(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
    )
    # one default brand_kit per brand
    op.execute(
        "CREATE UNIQUE INDEX uq_brand_kit_default ON brand_kit (brand_id) WHERE is_default = true"
    )

    # ---- creative_template ----
    op.create_table(
        "creative_template",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("creative_type", sa.String(32), nullable=True),
        sa.Column("spec", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_timestamps(),
    )

    # ---- creative_export ----
    op.create_table(
        "creative_export",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("creative_asset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("creative_asset.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_platform", sa.String(32), nullable=True),
        sa.Column("format_slug", sa.String(48), nullable=True),
        sa.Column("storage_backend", sa.String(16), nullable=True),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        *_timestamps(),
    )

    # ---- video_scene (subsystem) ----
    op.create_table(
        "video_scene",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("creative_project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("creative_project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_index", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("motion_hint", sa.Text(), nullable=True),
        sa.Column("duration_s", sa.Numeric(4, 1), nullable=False, server_default="8"),
        sa.Column("seed_image_key", sa.String(512), nullable=True),
        sa.Column("vo_line", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        *_timestamps(),
    )
    op.create_index("ix_video_scene_project_index", "video_scene",
                    ["creative_project_id", "scene_index"])

    # ---- video_render (subsystem — mirrors rendered_visuals) ----
    op.create_table(
        "video_render",
        _uuid_pk(), *_tenant_cols(),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("video_scene_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("video_scene.id", ondelete="CASCADE"), nullable=False),
        sa.Column("creative_project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("creative_project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_operation_id", sa.String(256), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("prompt_fingerprint", sa.String(64), nullable=True),
        sa.Column("storage_backend", sa.String(16), nullable=True),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("mime_type", sa.String(48), nullable=False, server_default="video/mp4"),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("fps", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("has_native_audio", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("synthid_watermark", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(16), nullable=False, server_default="submitted"),
        sa.Column("error_class", sa.String(255), nullable=True),
        sa.Column("cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.create_index("ix_video_render_operation", "video_render", ["provider_operation_id"])
    op.create_index("ix_video_render_project", "video_render", ["creative_project_id"])

    # ---- dormant RLS policies on the 9 tenant tables ----
    for table in _TENANT_TABLES:
        op.execute(rls.create_policy_sql(table))

    # ---- usage_event.kind CHECK += video kinds ----
    all_kinds = _USAGE_KINDS_AFTER_0033 + _NEW_USAGE_KINDS
    quoted = ", ".join(f"'{k}'" for k in all_kinds)
    op.execute("ALTER TABLE usage_event DROP CONSTRAINT IF EXISTS ck_usage_event_kind")
    op.execute(f"ALTER TABLE usage_event ADD CONSTRAINT ck_usage_event_kind CHECK (kind IN ({quoted}))")

    # ---- plan_quota seed for video_generation ----
    op.bulk_insert(
        sa.table("plan_quota", sa.column("plan_slug"), sa.column("usage_kind"), sa.column("monthly_limit")),
        [{"plan_slug": ps, "usage_kind": "video_generation", "monthly_limit": lim}
         for (ps, lim) in _VIDEO_QUOTAS],
    )

    # ---- RBAC: video.* permissions + grants to global system roles ----
    for slug, name, cat in _PERMISSIONS:
        op.execute(
            "INSERT INTO permissions (id, slug, name, description, category) "
            f"VALUES (gen_random_uuid(), '{slug}', '{name}', '{name}', '{cat}') "
            "ON CONFLICT (slug) DO NOTHING"
        )
    for role_slug, perm_slug in _GRANTS:
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) "
            f"SELECT r.id, p.id FROM roles r, permissions p "
            f"WHERE r.slug = '{role_slug}' AND p.slug = '{perm_slug}' "
            "ON CONFLICT DO NOTHING"
        )


def downgrade() -> None:
    # RBAC
    perm_slugs = ", ".join(f"'{s}'" for s, _, _ in _PERMISSIONS)
    op.execute(
        f"DELETE FROM role_permissions WHERE permission_id IN "
        f"(SELECT id FROM permissions WHERE slug IN ({perm_slugs}))"
    )
    op.execute(f"DELETE FROM permissions WHERE slug IN ({perm_slugs})")

    # plan_quota video rows
    op.execute("DELETE FROM plan_quota WHERE usage_kind = 'video_generation'")

    # usage CHECK back to the 0033 (8-kind) form
    quoted = ", ".join(f"'{k}'" for k in _USAGE_KINDS_AFTER_0033)
    op.execute("ALTER TABLE usage_event DROP CONSTRAINT IF EXISTS ck_usage_event_kind")
    op.execute(f"ALTER TABLE usage_event ADD CONSTRAINT ck_usage_event_kind CHECK (kind IN ({quoted}))")

    # RLS policies
    for table in _TENANT_TABLES:
        op.execute(rls.drop_policy_sql(table))

    # tables (children first)
    op.drop_table("video_render")
    op.drop_table("video_scene")
    op.drop_table("creative_export")
    op.drop_table("creative_template")
    op.execute("DROP INDEX IF EXISTS uq_brand_kit_default")
    op.drop_table("brand_kit")
    op.drop_table("creative_cost_event")
    op.drop_table("creative_variant")
    op.drop_table("creative_asset")
    op.drop_table("creative_project")
    op.drop_table("creative_format")
