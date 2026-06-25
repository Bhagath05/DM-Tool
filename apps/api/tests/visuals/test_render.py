"""Phase 8.4 — render.py rotation-history plumbing tests.

The renderer-level concept-family contract is pinned in
`test_render_prompt.py`. This file pins the THIN integration layer in
`render.py`:

  - `_recent_concept_families` correctly extracts concept-family slugs
    from prior `RenderedVisual.prompt` rows, in most-recent-first
    order, while silently skipping legacy (pre-8.4) prompts and any
    rows whose marker carries an unknown slug.

We don't have a Postgres test harness yet (see `tests/conftest.py`),
so this file mocks `AsyncSession.execute` rather than spinning up a
DB. The contract under test is pure: SQL row text in → rotation tuple
out.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aicmo.modules.visuals.render import _recent_concept_families
from aicmo.modules.visuals.render_prompt import (
    _CONCEPT_FAMILY_OPTIONS,
    build_image_prompt,
)
from tests.visuals.test_render_prompt import _brief, _profile

# ----------------------------------------------------------------------
#  Helpers
# ----------------------------------------------------------------------


def _make_session_returning(prompts: list[str | None]) -> Any:
    """Build an AsyncMock session whose `.execute(...).scalars().all()`
    returns the given list of stored prompt strings (most-recent first,
    matching how the production query is ordered).
    """
    session = MagicMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = prompts
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)
    return session


# ----------------------------------------------------------------------
#  _recent_concept_families behaviour
# ----------------------------------------------------------------------


class TestRecentConceptFamilies:
    @pytest.mark.asyncio
    async def test_returns_empty_tuple_when_brand_has_no_renders(self):
        session = _make_session_returning([])
        out = await _recent_concept_families(
            session, brand_id=uuid.uuid4(), limit=5
        )
        assert out == ()

    @pytest.mark.asyncio
    async def test_extracts_families_from_phase_84_prompts(self):
        # Build three real Phase 8.4 prompts with known concept
        # families baked in via the explicit brief field — the most
        # robust way to control what the marker will say.
        prompts = [
            build_image_prompt(
                brief={**_brief(), "concept_family": "social_proof"},
                profile=_profile(),
            ),
            build_image_prompt(
                brief={**_brief(), "concept_family": "authority_positioning"},
                profile=_profile(),
            ),
            build_image_prompt(
                brief={**_brief(), "concept_family": "lifestyle_aspiration"},
                profile=_profile(),
            ),
        ]
        session = _make_session_returning(prompts)
        out = await _recent_concept_families(
            session, brand_id=uuid.uuid4(), limit=5
        )
        # Most-recent first (same order the SQL query returns).
        assert out == (
            "social_proof",
            "authority_positioning",
            "lifestyle_aspiration",
        )

    @pytest.mark.asyncio
    async def test_skips_legacy_prompts_without_marker(self):
        # Legacy prompts (pre-8.4) have no `CONCEPT FAMILY — <slug>`
        # marker. The extractor must silently skip them — they
        # shouldn't poison the rotation history.
        legacy = "Some old prompt text with no marker line at all."
        new_prompt = build_image_prompt(
            brief={**_brief(), "concept_family": "behind_the_scenes"},
            profile=_profile(),
        )
        session = _make_session_returning([legacy, new_prompt, None, ""])
        out = await _recent_concept_families(
            session, brand_id=uuid.uuid4(), limit=5
        )
        # Only the real Phase 8.4 prompt survives.
        assert out == ("behind_the_scenes",)

    @pytest.mark.asyncio
    async def test_skips_contaminated_marker_with_unknown_slug(self):
        # A stored prompt that mentions the marker but with a slug we
        # don't recognise must NOT be passed through — stale schema
        # versions can't lock out a legitimate pick.
        contaminated = (
            "...preamble...\n"
            "CONCEPT FAMILY — not_a_real_family\n"
            "...rest of the prompt..."
        )
        valid_prompt = build_image_prompt(
            brief={**_brief(), "concept_family": "community"},
            profile=_profile(),
        )
        session = _make_session_returning([contaminated, valid_prompt])
        out = await _recent_concept_families(
            session, brand_id=uuid.uuid4(), limit=5
        )
        assert out == ("community",)

    @pytest.mark.asyncio
    async def test_preserves_db_order_most_recent_first(self):
        # We trust the SQL query's ORDER BY desc(created_at) — the
        # helper itself must not re-sort.
        prompts = [
            build_image_prompt(
                brief={**_brief(), "concept_family": f}, profile=_profile()
            )
            for f in (
                "offer_driven",  # newest
                "customer_testimonial",
                "problem_awareness",
                "social_proof",
                "lifestyle_aspiration",  # oldest
            )
        ]
        session = _make_session_returning(prompts)
        out = await _recent_concept_families(
            session, brand_id=uuid.uuid4(), limit=5
        )
        assert out == (
            "offer_driven",
            "customer_testimonial",
            "problem_awareness",
            "social_proof",
            "lifestyle_aspiration",
        )

    @pytest.mark.asyncio
    async def test_helper_uses_the_limit_parameter(self):
        # `limit` is plumbed into the SELECT — verify by inspecting
        # the SQL the helper actually issued.
        session = _make_session_returning([])
        await _recent_concept_families(
            session, brand_id=uuid.uuid4(), limit=12
        )
        assert session.execute.call_count == 1
        stmt = session.execute.call_args.args[0]
        # SQLAlchemy `Select.limit` stores the value on `_limit_clause`.
        # The simplest stable assertion: the compiled SQL contains "LIMIT".
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 12" in compiled.upper()


# ----------------------------------------------------------------------
#  End-to-end: extracted history actually drives the rotation
# ----------------------------------------------------------------------


class TestRotationDrivesNextRender:
    @pytest.mark.asyncio
    async def test_next_render_avoids_every_recently_extracted_family(self):
        # The full Phase 8.4 round-trip: build N prompts, extract
        # their families via the helper, feed them back to the
        # renderer, and confirm the next pick avoids every one.
        recent_families = (
            "lifestyle_aspiration",
            "social_proof",
            "customer_transformation",
        )
        prompts = [
            build_image_prompt(
                brief={**_brief(), "concept_family": f}, profile=_profile()
            )
            for f in recent_families
        ]
        session = _make_session_returning(prompts)
        out = await _recent_concept_families(
            session, brand_id=uuid.uuid4(), limit=5
        )
        assert out == recent_families

        # Now hand `out` to a fresh render and confirm the pick avoids
        # every entry.
        next_prompt = build_image_prompt(
            brief=_brief(goal="Book a table this weekend"),
            profile=_profile(industry="Restaurant"),
            recent_concept_families=out,
        )
        # The marker in the new prompt names the chosen slug — it
        # must not be in the recent set.
        from aicmo.modules.visuals.render_prompt import extract_concept_family

        chosen = extract_concept_family(next_prompt)
        assert chosen is not None
        assert chosen not in out
        assert chosen in _CONCEPT_FAMILY_OPTIONS
