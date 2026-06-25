"""Phase 1 — auto-render after generate."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aicmo.modules.visuals.render import auto_render_visual
from aicmo.modules.visuals.render_prompt import (
    ad_output_to_brief,
    brief_dict_for_render,
)
from aicmo.providers.images.base import ImageRenderResult
from aicmo.tenancy.context import TenantContext
from tests.visuals.test_render_prompt import _profile

_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _fake_provider():
    class FakeProvider:
        name = "openai"

        async def render(self, request):
            return ImageRenderResult(
                image_bytes=_MINIMAL_PNG,
                mime_type="image/png",
                width=1024,
                height=1024,
                provider_image_id="fake",
                cost_cents=4,
                latency_ms=100,
                provider_name="openai",
            )

    return FakeProvider()


def _tenant() -> TenantContext:
    uid = uuid.uuid4()
    return TenantContext(
        user_id=str(uid),
        user_uuid=uid,
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        member_id=uid,
    )


def _visual_row(*, visual_type: str, output: dict[str, Any]):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.visual_type = visual_type
    row.output = output
    row.platform = "instagram"
    return row


class TestBriefDictForRender:
    def test_carousel_slide_maps_focal_subject(self):
        output = {
            "aspect_ratio": "4:5",
            "cover_concept": "cover",
            "cta_slide_concept": "book now",
            "design_system_palette": [{"name": "A", "hex": "#111", "role": "bg"}],
            "design_system_typography": {"style": "bold"},
            "slide_designs": [
                {"slide_number": 1, "visual": "hero dish", "text_treatment": "big"},
                {"slide_number": 2, "visual": "chef", "text_treatment": "small"},
            ],
        }
        brief = brief_dict_for_render(
            visual_type="carousel", output=output, slide_index=0
        )
        assert "hero dish" in brief["focal_subject"]
        assert brief["aspect_ratio"] == "4:5"

    def test_thumbnail_maps_focal(self):
        output = {
            "aspect_ratio": "16:9",
            "focal_subject": "smiling founder",
            "contrast_strategy": "neon pop",
            "typography": {"style": "bold"},
            "mobile_legibility_note": "reads at small size",
        }
        brief = brief_dict_for_render(visual_type="thumbnail", output=output)
        assert brief["focal_subject"] == "smiling founder"

    def test_ad_output_to_brief_uses_creative_direction(self):
        brief = ad_output_to_brief(
            ad_type="meta",
            output={
                "creative_direction": "Product on marble counter",
                "headline": "Shop now",
            },
        )
        assert "marble" in brief["focal_subject"]


class TestAutoRenderVisual:
    @pytest.mark.asyncio
    async def test_renders_ad_creative(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        with (
            patch(
                "aicmo.modules.visuals.render.get_image_provider",
                return_value=_fake_provider(),
            ),
            patch(
                "aicmo.modules.visuals.render.get_quota",
                new_callable=AsyncMock,
                return_value=MagicMock(remaining=10, daily_cap=20),
            ),
            patch(
                "aicmo.modules.visuals.render._recent_concept_families",
                new_callable=AsyncMock,
                return_value=(),
            ),
        ):
            output = {
                "aspect_ratio": "1:1",
                "focal_subject": "product hero",
                "composition_layout": "centered",
                "color_palette": [],
                "typography": {},
                "visual_hierarchy": ["a", "b", "c"],
                "cta_placement": "bottom",
                "mood_keywords": ["premium"],
                "reference_aesthetic": "editorial",
            }
            visual = _visual_row(visual_type="ad_creative", output=output)
            renders = await auto_render_visual(
                session,
                tenant=_tenant(),
                visual=visual,
                profile=_profile(),
            )
        assert len(renders) == 1
        assert renders[0].signed_url.startswith("/api/v1/media/")

    @pytest.mark.asyncio
    async def test_renders_all_carousel_slides(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        with (
            patch(
                "aicmo.modules.visuals.render.get_image_provider",
                return_value=_fake_provider(),
            ),
            patch(
                "aicmo.modules.visuals.render.get_quota",
                new_callable=AsyncMock,
                return_value=MagicMock(remaining=10, daily_cap=20),
            ),
            patch(
                "aicmo.modules.visuals.render._recent_concept_families",
                new_callable=AsyncMock,
                return_value=(),
            ),
        ):
            output = {
                "aspect_ratio": "1:1",
                "cover_concept": "cover",
                "cta_slide_concept": "cta",
                "design_system_palette": [],
                "design_system_typography": {},
                "slide_designs": [
                    {"slide_number": 1, "visual": "a", "text_treatment": "t"},
                    {"slide_number": 2, "visual": "b", "text_treatment": "t"},
                    {"slide_number": 3, "visual": "c", "text_treatment": "t"},
                ],
            }
            visual = _visual_row(visual_type="carousel", output=output)
            renders = await auto_render_visual(
                session,
                tenant=_tenant(),
                visual=visual,
                profile=_profile(),
            )
        assert len(renders) == 3
        assert renders[0].slide_index == 0
        assert renders[2].slide_index == 2

    @pytest.mark.asyncio
    async def test_skips_reel_type(self):
        session = MagicMock()
        visual = _visual_row(visual_type="reel", output={"scenes": []})
        renders = await auto_render_visual(
            session,
            tenant=_tenant(),
            visual=visual,
            profile=_profile(),
        )
        assert renders == []
