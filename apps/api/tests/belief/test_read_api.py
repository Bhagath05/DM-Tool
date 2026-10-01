"""Phase 3D — read-only belief API (wiring + projection + auth boundary).

Route wiring and the pure projection run without Postgres; the
unauthenticated-401 assertion is Postgres-gated (session resolution needs a DB).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest

from aicmo.modules.belief import read
from aicmo.modules.belief.schemas import BeliefResolution, BeliefView

_ORIGIN = "https://dm-tool-web.vercel.app"


def _client() -> httpx.AsyncClient:
    from aicmo.main import app

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://testserver",
        headers={"origin": _ORIGIN},
    )


def _view(*, status="active", confidence=60, effective=None, superseded_by=None):
    now = datetime.now(UTC)
    return BeliefView(
        id=uuid.uuid4(),
        category="channel",
        subject_key="reels_vs_static",
        statement="Reels engaged more for this audience.",
        scope={"channel": "instagram"},
        status=status,
        confidence=confidence,
        confidence_reason="2 supporting (observational)",
        effective_confidence=effective,
        freshness_reason="aged" if effective is not None else None,
        evidence_count=2,
        validated_at=now,
        valid_from=now,
        valid_until=None,
        superseded_by_id=superseded_by,
        parent_belief_id=None,
        created_at=now,
        updated_at=now,
        evidence=[],
    )


# --- wiring -----------------------------------------------------------------
def test_belief_route_registered():
    from aicmo.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/v1/beliefs" in paths


def test_belief_api_is_read_only():
    from aicmo.main import app

    for r in app.routes:
        if getattr(r, "path", None) == "/api/v1/beliefs":
            methods = getattr(r, "methods", set()) or set()
            assert methods <= {"GET", "HEAD"}  # no POST/PUT/PATCH/DELETE write path


# --- projection (pure) ------------------------------------------------------
def test_projection_prefers_effective_confidence_and_keeps_original():
    resolution = BeliefResolution(
        brand_id=uuid.uuid4(), active=[_view(confidence=80, effective=48)]
    )
    now = datetime.now(UTC)
    out = read.to_read_response(resolution, now=now, includes_history=False)
    card = out.active[0]
    assert card.confidence == 48  # freshness-adjusted, shown to the user
    assert card.original_confidence == 80  # honesty: what evidence supported
    assert card.is_current is True
    assert card.subject == "reels_vs_static"
    assert out.as_of == now and out.includes_history is False


def test_projection_marks_history_not_current():
    superseded = _view(status="superseded", superseded_by=uuid.uuid4())
    contradicted = _view(status="contradicted")
    resolution = BeliefResolution(
        brand_id=uuid.uuid4(), superseded=[superseded], contradicted=[contradicted]
    )
    out = read.to_read_response(resolution, now=datetime.now(UTC), includes_history=True)
    assert out.active == []
    assert len(out.historical) == 2
    assert all(c.is_current is False for c in out.historical)


def test_projection_falls_back_to_stored_confidence_when_no_freshness():
    resolution = BeliefResolution(
        brand_id=uuid.uuid4(), active=[_view(confidence=55, effective=None)]
    )
    out = read.to_read_response(resolution, now=datetime.now(UTC), includes_history=False)
    assert out.active[0].confidence == 55 and out.active[0].original_confidence == 55


# --- auth boundary (PG-gated) ----------------------------------------------
@pytest.mark.asyncio
async def test_belief_api_requires_auth():
    from tests._dbtest import pg_reachable

    if not pg_reachable():
        pytest.skip("Postgres not reachable")

    async with _client() as c:
        r = await c.get("/api/v1/beliefs")
        assert r.status_code == 401
        r = await c.get("/api/v1/beliefs?include_history=true")
        assert r.status_code == 401
