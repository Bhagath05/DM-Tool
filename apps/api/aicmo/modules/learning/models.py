"""ORM models for the Learning Lab.

Design rules (mirroring `social/models.py`):
- Every table carries `created_at` / `updated_at` via TimestampMixin.
- Loose `raw_*_json` JSONB columns hold the unflattened payload so we
  never lose data we might want to mine later.
- All three tables expose `sample_size`, `confidence_score`, and an
  `evidence` JSONB blob — those are the fields the frontend's
  WhyGeneratedCard reads to *show its work*. Hide them and the whole
  premise of the feature collapses.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aicmo.db.base import Base, TenantMixin, TimestampMixin


class CampaignExperiment(Base, TimestampMixin, TenantMixin):
    """Provenance row — written once per generation.

    The generator (content / ads / visuals / landing-pages / bundles)
    calls `learning.service.record_experiment(...)` immediately after it
    persists the asset. That call captures:

    - which inherited patterns the LLM was shown,
    - the *variable choices* it ended up making (hook style, format,
      tone, length, platform, CTA),
    - a compact snapshot of the GenerationContext at the time,
    - a short LLM-written `hypothesis` predicting why this should work.

    The point: when results come in later, we can attribute outcomes to
    decisions rather than guessing. That's the whole `WhyGeneratedCard`
    and the whole feedback loop.
    """

    __tablename__ = "campaign_experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)

    # What was generated. Mirrors analytics' (source_asset_type,
    # source_asset_id) tuple so we can JOIN on it later.
    source_asset_type: Mapped[str] = mapped_column(
        String(32), index=True
    )  # content | ad | visual | landing_page | bundle
    source_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True
    )

    # Optional dimensions — useful for slicing experiments in the Lab UI.
    platform: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The LLM's one-line prediction. Read aloud on the result card:
    # "We expect this to outperform because founder-led hooks beat
    # product showcases 2.3x for this audience."
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Inherited winning-pattern summaries that fed into this generation.
    # Stored as plain strings so the UI can render without joining back
    # to WinningPattern (which may evolve under us).
    inherited_patterns: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )

    # The actual creative dimensions chosen. Free-shape JSONB because
    # each asset type has different relevant axes (a reel has hook +
    # format + length; a landing page has hero + CTA + form-length).
    # Keys we conventionally use: hook_style, format, tone, length,
    # cta_style, visual_style, posting_time.
    variable_choices: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    # Compact copy of the GenerationContext at the time — *not* the full
    # thing (we don't need to re-store the whole brand profile per gen).
    # See learning.service for the trimming rules.
    context_snapshot: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    # pending → live (asset distributed) → completed (we have results)
    # → archived (user dismissed).
    status: Mapped[str] = mapped_column(
        String(16),
        default="pending",
        server_default="pending",
        index=True,
    )

    # Same triple of evidence fields as LearningEvent so the frontend can
    # treat experiments + events uniformly when rendering provenance.
    sample_size: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    confidence_score: Mapped[float] = mapped_column(
        Numeric(3, 2), default=0.5, server_default="0.5"
    )
    evidence: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )


class ExperimentResult(Base, TimestampMixin):
    """Performance snapshot for an experiment.

    One experiment can have multiple result rows over time — we
    re-snapshot weekly so the Lab UI can plot how a piece aged. For MVP
    we only insert one row per experiment (latest); the design allows
    multiple later (same shape as PerformanceSignal in `social/`).
    """

    __tablename__ = "experiment_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaign_experiments.id", ondelete="CASCADE"),
        index=True,
    )

    # Distribution / reach metrics.
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)

    # Engagement.
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)

    # Conversion — the bottom-of-funnel metric that actually matters.
    # Pulled from analytics.leads attributed to this asset.
    leads: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)

    # Video-only.
    views: Mapped[int] = mapped_column(Integer, default=0)
    watch_time_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    raw_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )

    # Same triple of evidence fields so the UI can score how
    # representative this snapshot is. `sample_size` here is impressions
    # at the time the snapshot was taken — small samples shouldn't drive
    # confident conclusions.
    sample_size: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    confidence_score: Mapped[float] = mapped_column(
        Numeric(3, 2), default=0.5, server_default="0.5"
    )
    evidence: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )


class LearningEvent(Base, TimestampMixin, TenantMixin):
    """The most important table in this module.

    These rows are what GenerationContext inherits — the "what have we
    learned from our own generations?" layer that sits next to Social
    Intelligence's "what works on your platform organically?".

    Each LearningEvent is one *evidence-backed* insight. The Learning
    Engine (LLM) clusters experiments + results, looks for variables
    that moved outcomes, and writes a short finding with a confidence
    score and a list of supporting experiment IDs. Low-evidence findings
    (sample_size < 3, confidence < 0.4) are stored but hidden from the
    generator — we never want to "learn" from noise.
    """

    __tablename__ = "learning_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), index=True)

    # The dimension this finding speaks to. Conventional values:
    # hook_style | format | tone | length | platform | cta_style |
    # visual_style | posting_time | offer | audience_segment.
    variable: Mapped[str] = mapped_column(String(64), index=True)

    # The human-readable insight, e.g. "Before/after hooks beat product
    # showcases 2.3x in saves on Instagram for this audience (n=12)."
    finding: Mapped[str] = mapped_column(Text)

    # "positive" | "negative" | "neutral" — drives icon + colour in UI.
    direction: Mapped[str] = mapped_column(
        String(16), default="positive", server_default="positive"
    )

    # Numerical effect size if the LLM could estimate one (e.g. 2.3 for
    # "2.3x lift"). Kept as float; null when we only have a qualitative
    # observation.
    effect_size: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    # Which experiments fed this finding. UUID strings in JSONB so we
    # don't need a join table; auditable from the Lab UI.
    experiment_ids: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )

    # Free-form supporting bullets the LLM wrote — what changed, what
    # held constant, the rough math. Same shape as the evidence field on
    # the other two tables for uniformity in the frontend.
    evidence: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )

    # n of experiments backing this finding. The Learning Engine refuses
    # to emit at n < 3 unless an extreme effect makes it worth showing.
    sample_size: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    # 0.00 – 1.00. Computed from n + effect-size + variance.
    confidence_score: Mapped[float] = mapped_column(
        Numeric(3, 2), default=0.5, server_default="0.5"
    )

    # "auto" (LLM-derived from clustering) | "manual" (user marked an
    # experiment as a winner). Manual events get higher trust weight.
    source: Mapped[str] = mapped_column(
        String(16), default="auto", server_default="auto"
    )

    # active → archived (user dismissed) | superseded (a newer event
    # contradicted it). Archived events don't feed the context.
    status: Mapped[str] = mapped_column(
        String(16),
        default="active",
        server_default="active",
        index=True,
    )
