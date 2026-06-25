"""Backward compatibility for partial visual strategy JSONB on list endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from aicmo.modules.visuals.schemas import (
    GeneratedVisualResponse,
    ad_strategy_to_visual_strategy,
    normalize_visual_strategy,
)


class TestNormalizeVisualStrategy:
    def test_fills_missing_fields_for_legacy_row(self):
        out = normalize_visual_strategy({"visual_concept": "Hero dessert shot"})
        assert out["visual_concept"] == "Hero dessert shot"
        assert out["emotional_trigger"] == "Not recorded"
        assert out["audience_angle"] == "Not recorded"
        assert out["trend_influence"] == "none"
        assert out["composition_principle"] == "Not recorded"
        assert out["conversion_rationale"] == "Not recorded"

    def test_preserves_complete_strategy(self):
        full = {
            "visual_concept": "A",
            "emotional_trigger": "desire",
            "audience_angle": "foodies",
            "trend_influence": "UGC food",
            "composition_principle": "rule of thirds",
            "conversion_rationale": "Drives orders",
        }
        assert normalize_visual_strategy(full) == full


class TestGeneratedVisualResponseCompat:
    def test_validates_orm_row_with_partial_strategy(self):
        row = SimpleNamespace(
            id=uuid.uuid4(),
            user_id="dev-user",
            business_profile_id=uuid.uuid4(),
            trend_report_id=None,
            landing_page_id=None,
            visual_type="ad_creative",
            platform="Instagram",
            goal="Test",
            tone="Professional",
            strategy={"visual_concept": "Companion render only"},
            output={},
            is_saved=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        resp = GeneratedVisualResponse.model_validate(row)
        assert resp.strategy.visual_concept == "Companion render only"
        assert resp.strategy.emotional_trigger == "Not recorded"

    def test_service_to_response_with_mock_row(self):
        from aicmo.modules.visuals.service import _to_response

        row = MagicMock()
        row.id = uuid.uuid4()
        row.user_id = "dev-user"
        row.business_profile_id = uuid.uuid4()
        row.trend_report_id = None
        row.landing_page_id = None
        row.visual_type = "ad_creative"
        row.platform = "Instagram"
        row.goal = "Test"
        row.tone = "Professional"
        row.strategy = {"visual_concept": "Legacy partial"}
        row.output = {}
        row.is_saved = False
        row.created_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)

        resp = _to_response(row)
        assert resp.strategy.audience_angle == "Not recorded"


class TestAdStrategyMapping:
    def test_maps_ad_fields_to_visual_strategy(self):
        out = ad_strategy_to_visual_strategy(
            {
                "emotional_trigger": "FOMO",
                "audience_angle": "Dessert lovers",
                "trend_influence": "UGC",
                "conversion_strategy": "Order now",
            },
            visual_concept="Weekend lineup",
        )
        assert out["visual_concept"] == "Weekend lineup"
        assert out["emotional_trigger"] == "FOMO"
        assert out["conversion_rationale"] == "Order now"
