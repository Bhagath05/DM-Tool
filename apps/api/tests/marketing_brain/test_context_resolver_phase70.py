"""Phase 7.0 — Business Context Resolver additions (unit, no DB).

Covers the new, reuse-first surface: current marketing strategy, brand voice,
and the explicit provenance legend. Isolation/provenance over the real DB is
pinned separately in test_context_resolver_integration.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from aicmo.modules.marketing_brain.provenance import (
    ContextProvenance,
    provenance_legend_block,
)
from aicmo.modules.marketing_brain.schemas import (
    MarketingBrainContext,
    MarketingBrainProfileSnapshot,
    MarketingBrainStrategySnapshot,
)
from aicmo.modules.marketing_brain.service import (
    build_profile_snapshot,
    context_to_prompt_block,
    to_strategy_snapshot,
)


def _profile_row(**over):
    base = dict(
        business_name="Acme",
        website=None,
        industry="Bakery",
        business_type=None,
        target_audience="locals",
        business_location=None,
        competitors=[],
        monthly_budget_band=None,
        primary_goal_text="leads",
        products=[],
        services=[],
        pricing=None,
        goals=["get leads"],
        preferred_platforms=["instagram"],
        brand_tone="friendly",
    )
    base.update(over)
    return SimpleNamespace(**base)


# --- strategy snapshot ------------------------------------------------------
def test_strategy_snapshot_present_from_record():
    rec = SimpleNamespace(
        strategy={
            "positioning": "Small-batch bakery for busy locals",
            "target_summary": "Office workers near downtown",
            "recommendation": "Publish a lead page and promote it",
        },
        status="completed",
        created_at=datetime.now(UTC),
    )
    snap = to_strategy_snapshot(rec)
    assert snap.present is True
    assert snap.status == "completed"
    assert "Small-batch" in (snap.positioning or "")
    assert "lead page" in (snap.recommendation or "")


def test_strategy_snapshot_absent_is_not_fabricated():
    assert to_strategy_snapshot(None).present is False
    assert to_strategy_snapshot(SimpleNamespace(strategy=None)).present is False
    assert to_strategy_snapshot(SimpleNamespace(strategy={})).present is False


# --- brand voice ------------------------------------------------------------
def test_profile_snapshot_surfaces_brand_voice():
    snap = build_profile_snapshot(_profile_row(brand_tone="playful"))
    assert snap.brand_voice == "playful"


def test_profile_snapshot_missing_brand_tone_is_none():
    # A row that otherwise resolves but lacks brand_tone → brand_voice None,
    # never an error (getattr-guarded).
    row = _profile_row()
    del row.brand_tone
    snap = build_profile_snapshot(row)
    assert snap.brand_voice is None


# --- provenance legend + prompt rendering -----------------------------------
def test_provenance_legend_lists_all_five_tiers():
    legend = provenance_legend_block()
    for tier in ContextProvenance:
        assert tier.value in legend


def _ctx(**over) -> MarketingBrainContext:
    base = dict(
        brand_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        built_at=datetime.now(UTC),
        profile=MarketingBrainProfileSnapshot(present=True, business_name="Acme", brand_voice="friendly"),
        strategy=MarketingBrainStrategySnapshot(
            present=True,
            positioning="Small-batch bakery",
            target_summary="locals",
            recommendation="Publish a lead page",
        ),
    )
    base.update(over)
    return MarketingBrainContext(**base)


def test_prompt_block_includes_provenance_legend_and_strategy_and_voice():
    block = context_to_prompt_block(_ctx())
    assert "PROVENANCE TIERS" in block
    assert "USER_STATED" in block and "MEASURED" in block
    assert "CURRENT STRATEGY" in block
    assert "Small-batch bakery" in block
    assert "Publish a lead page" in block
    assert "Brand voice (USER_STATED): friendly" in block


def test_prompt_block_absent_strategy_is_explicit_not_invented():
    block = context_to_prompt_block(_ctx(strategy=MarketingBrainStrategySnapshot(present=False)))
    assert "CURRENT STRATEGY: none yet" in block
