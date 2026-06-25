"""CS1-6 — studio stubs (AI router, composer) + the flag gate.

The full service flow (create→ai-edit→pro-edit→revert→transform→restyle with
metering + audit) is verified live against Postgres; these pin the CI-safe
pure pieces + the dark-launch gate.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from aicmo.config import get_settings
from aicmo.modules.creative.design import ai_router, transform
from aicmo.modules.creative.design.layer_schema import validate_doc
from aicmo.modules.creative.design.ops import apply_ops, parse_ops
from aicmo.modules.creative.design.router import _require_enabled


# ---- AI Edit Router classifier (stub, Law-2: keys on action not industry) ----
@pytest.mark.parametrize("instruction,expected", [
    ("make it luxury", "restyle"),
    ("give it a modern vibe", "restyle"),
    ("convert this to an Instagram story", "transform"),
    ("make this for LinkedIn", "transform"),
    ("regenerate this", "regenerate"),
    ("change the headline to Summer Sale", "edit"),
])
def test_classify(instruction, expected):
    assert ai_router.classify(instruction) == expected


# ---- stub composer produces a schema-valid on-brand doc ----
def test_stub_compose_is_valid():
    doc = transform.stub_compose(format_slug="meta_ads", headline="Hi", subhead="Sub", cta="Buy")
    validate_doc(doc)  # raises if invalid
    roles = {l["role"] for l in doc["pages"][0]["layers"]}
    assert {"headline", "subhead", "cta"} <= roles
    assert doc["format_slug"] == "meta_ads"


def test_stub_compose_empty_is_valid():
    doc = transform.stub_compose(format_slug=None)
    validate_doc(doc)
    assert doc["pages"][0]["layers"] == []


# ---- stub edit ops apply + revalidate ----
def test_stub_edit_ops_set_existing_text():
    doc = transform.stub_compose(format_slug="meta_ads", headline="Old")
    ops = ai_router.stub_edit_ops(doc, "New headline copy")
    out = apply_ops(doc, parse_ops(ops))
    validate_doc(out)
    assert out["pages"][0]["layers"][0]["text"] == "New headline copy"


def test_stub_edit_ops_adds_body_when_no_text():
    doc = transform.stub_compose(format_slug=None)  # no layers
    ops = ai_router.stub_edit_ops(doc, "Add this line")
    out = apply_ops(doc, parse_ops(ops))
    validate_doc(out)
    assert out["pages"][0]["layers"][0]["text"] == "Add this line"


# ---- transform/restyle stubs are derive-only ----
def test_transform_reformat_changes_format_only():
    doc = transform.stub_compose(format_slug="meta_ads", headline="Hi")
    out = transform.stub_transform_doc(doc, "reformat", "instagram_reels")
    assert out["format_slug"] == "instagram_reels"
    assert out["pages"][0]["layers"] == doc["pages"][0]["layers"]  # message preserved
    assert doc["format_slug"] == "meta_ads"  # source untouched (pure)


# ---- flag gate (disabled → 409, enabled → pass) ----
def test_studio_disabled_raises_409(monkeypatch):
    # Explicit false (an env var overrides the dev .env which now defaults true).
    monkeypatch.setenv("STUDIO_ENABLED", "false")
    get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as ei:
            _require_enabled()
        assert ei.value.status_code == 409
    finally:
        monkeypatch.delenv("STUDIO_ENABLED", raising=False)
        get_settings.cache_clear()


def test_studio_enabled_does_not_raise(monkeypatch):
    monkeypatch.setenv("STUDIO_ENABLED", "true")
    get_settings.cache_clear()
    try:
        _require_enabled()  # no raise
    finally:
        monkeypatch.delenv("STUDIO_ENABLED", raising=False)
        get_settings.cache_clear()
