"""HTTP surface for danger-zone routes — must not 404."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from aicmo.main import app


@pytest.mark.asyncio
async def test_reset_and_purge_routes_are_registered_not_404() -> None:
    org_id = uuid.uuid4()
    # Routing is resolved before the handler touches the DB, so this test
    # proves registration independent of DB availability. Let a handler
    # exception surface as a 500 response (not re-raised) so "not 404" is
    # still checkable when Postgres is absent — a 500 proves the route exists.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reset = await client.post(f"/api/v1/orgs/{org_id}/reset")
        purge = await client.post(f"/api/v1/orgs/{org_id}/purge")

    assert reset.status_code != 404, reset.text
    assert purge.status_code != 404, purge.text
