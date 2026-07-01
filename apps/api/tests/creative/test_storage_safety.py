"""Production storage-safety guard + R2 future-readiness.

Pins the rule: assets are never silently written to ephemeral local disk
in production. `media_persistence_available` is the single source of
truth; the local backend refuses to write when it's false; the registry
selects the S3-compatible backend for both `s3` and `r2`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aicmo.config import Settings
from aicmo.modules.creative.storage import local, registry
from aicmo.modules.creative.storage.base import MediaPersistenceUnavailable


def _settings(**kw) -> Settings:
    # model_construct skips env/.env + validation so the pure property is
    # tested in isolation (no DATABASE_URL etc. required).
    return Settings.model_construct(**kw)


# ---- media_persistence_available ----------------------------------------


def test_local_in_production_is_not_persistent():
    assert (
        _settings(media_backend="local", api_env="production").media_persistence_available
        is False
    )


@pytest.mark.parametrize("env", ["development", "staging"])
def test_local_off_production_is_fine(env):
    assert (
        _settings(media_backend="local", api_env=env).media_persistence_available is True
    )


@pytest.mark.parametrize("backend", ["s3", "r2"])
def test_durable_backend_in_production_is_persistent(backend):
    assert (
        _settings(media_backend=backend, api_env="production").media_persistence_available
        is True
    )


# ---- registry selection (R2 future-readiness) ---------------------------


@pytest.mark.parametrize(
    "backend,expected_name",
    [("local", "local"), ("s3", "s3"), ("r2", "s3")],
)
def test_registry_selects_backend_by_env(monkeypatch, backend, expected_name):
    monkeypatch.setattr(
        registry, "get_settings", lambda: SimpleNamespace(media_backend=backend)
    )
    assert registry.get_storage_backend().name == expected_name


# ---- local backend write backstop ---------------------------------------


def test_local_put_refuses_when_persistence_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        local,
        "get_settings",
        lambda: SimpleNamespace(
            media_persistence_available=False, media_dir=str(tmp_path)
        ),
    )
    with pytest.raises(MediaPersistenceUnavailable):
        local.LocalDiskBackend().put(key="o/x.png", data=b"bytes", content_type="image/png")
    # And nothing was written — the asset is never silently orphaned.
    assert not list(tmp_path.rglob("*.png"))


def test_local_put_writes_when_persistence_available(monkeypatch, tmp_path):
    monkeypatch.setattr(
        local,
        "get_settings",
        lambda: SimpleNamespace(
            media_persistence_available=True, media_dir=str(tmp_path)
        ),
    )
    ref = local.LocalDiskBackend().put(
        key="o/x.png", data=b"bytes", content_type="image/png"
    )
    assert ref.backend == "local"
    assert list(tmp_path.rglob("*.png"))


# ---- visuals render path (ads + creatives) honours the same gate ---------


@pytest.mark.asyncio
async def test_visuals_render_refuses_when_persistence_unavailable(monkeypatch):
    """The visuals store writes to media_dir directly (separate from the
    creative-storage backend). It must apply the same gate — and fail BEFORE
    the paid image-provider call, not after silently losing the file."""
    from aicmo.modules.visuals import render as render_mod

    monkeypatch.setattr(
        render_mod,
        "get_settings",
        lambda: SimpleNamespace(media_persistence_available=False),
    )
    # Dummy args are never touched: the guard raises right after get_settings().
    with pytest.raises(MediaPersistenceUnavailable):
        await render_mod._render_single_png(
            None,
            tenant=None,
            visual_id=None,
            visual=None,
            profile=None,
            brief={},
            quality="standard",
            recent_concept_families=(),
            slide_index=None,
        )
