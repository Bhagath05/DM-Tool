"""Shared pytest fixtures.

Kept minimal — we don't yet have a Postgres test harness, so most
backend tests are pure-function unit tests. When we add a Postgres
fixture later, it'll live here.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _env_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin API_ENV=development so tests don't trip the production guard."""
    monkeypatch.setenv("API_ENV", "development")
    # Clear any cached settings so the next get_settings() picks up the env.
    from aicmo.config import get_settings

    get_settings.cache_clear()
