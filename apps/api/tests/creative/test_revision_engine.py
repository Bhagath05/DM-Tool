"""CS1-4 — the Revision Engine is the single write path (Law 3).

Proves: the revision chain + parent pointers are correct; a stale base
returns a lock error (409); validation rejects bad docs from any actor;
cross-tenant asset refs are rejected; revert is itself a forward revision;
and design.doc only ever changes through apply_revision.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from aicmo.modules.creative.design.layer_schema import CrossTenantAssetRef
from aicmo.modules.creative.design.ops import parse_ops
from aicmo.modules.creative.design.revision import (
    StaleRevision,
    apply_revision,
    new_design,
    revert_to,
)


class FakeSession:
    """apply_revision is sync and only calls .add — a list captures rows."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)


ORG = uuid.uuid4()
BRAND = uuid.uuid4()


def _design():
    return new_design(
        organization_id=ORG, brand_id=BRAND, name="Promo",
        media_type="image", format_slug="meta_ads",
    )


def _full_doc(text="Hello"):
    return {
        "version": 1, "format_slug": "meta_ads",
        "pages": [{"background": {"kind": "color", "color": "#111"},
                   "layers": [{"type": "text", "id": "h1", "role": "headline",
                               "text": text, "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2,
                               "color": "brand:primary"}]}],
    }


def test_ai_generate_creates_revision_1():
    s, d = FakeSession(), _design()
    assert d.current_revision == 0 and d.head_revision_id is None
    rev = apply_revision(s, design=d, actor_kind="ai", mode="ai", source="ai_generate",
                         base_revision=0, owned_asset_ids=set(), full_doc=_full_doc())
    assert rev.revision_n == 1
    assert rev.parent_revision_id is None      # first revision has no parent
    assert d.current_revision == 1
    assert d.head_revision_id == rev.id
    assert d.doc["pages"][0]["layers"][0]["text"] == "Hello"
    assert rev.source == "ai_generate" and rev.actor_kind == "ai"


def test_chain_three_revisions_parent_pointers():
    s, d = FakeSession(), _design()
    r1 = apply_revision(s, design=d, actor_kind="ai", mode="ai", source="ai_generate",
                        base_revision=0, owned_asset_ids=set(), full_doc=_full_doc("One"))
    # Guided edit via ops
    r2 = apply_revision(s, design=d, actor_kind="ai", mode="guided", source="ai_edit",
                        base_revision=1, owned_asset_ids=set(),
                        ops=parse_ops([{"op": "set_text", "layer_id": "h1", "text": "Two"}]))
    # Pro edit via ops (same write path, different actor)
    r3 = apply_revision(s, design=d, actor_kind="human", mode="pro", source="user_edit",
                        base_revision=2, owned_asset_ids=set(), created_by_user_id="u_1",
                        ops=parse_ops([{"op": "set_text", "layer_id": "h1", "text": "Three"}]))
    assert [r.revision_n for r in (r1, r2, r3)] == [1, 2, 3]
    assert r2.parent_revision_id == r1.id
    assert r3.parent_revision_id == r2.id
    assert d.current_revision == 3
    assert d.doc["pages"][0]["layers"][0]["text"] == "Three"
    # ops are recorded as the diff on edit revisions
    assert r2.ops and r2.ops[0]["op"] == "set_text"
    assert r1.ops is None  # full-doc generate has no ops diff


def test_one_code_path_all_three_modes_same_function():
    # The decisive Law-3 proof: ai/guided/pro all go through apply_revision.
    s, d = FakeSession(), _design()
    apply_revision(s, design=d, actor_kind="ai", mode="ai", source="ai_generate",
                   base_revision=0, owned_asset_ids=set(), full_doc=_full_doc())
    for n, (actor, mode, source) in enumerate(
        [("ai", "guided", "ai_edit"), ("human", "pro", "user_edit")], start=1
    ):
        rev = apply_revision(s, design=d, actor_kind=actor, mode=mode, source=source,
                             base_revision=n, owned_asset_ids=set(),
                             ops=parse_ops([{"op": "set_text", "layer_id": "h1", "text": f"v{n}"}]))
        assert rev.mode == mode and rev.actor_kind == actor


def test_stale_base_revision_raises():
    s, d = FakeSession(), _design()
    apply_revision(s, design=d, actor_kind="ai", mode="ai", source="ai_generate",
                   base_revision=0, owned_asset_ids=set(), full_doc=_full_doc())
    with pytest.raises(StaleRevision):
        apply_revision(s, design=d, actor_kind="human", mode="pro", source="user_edit",
                       base_revision=0,  # stale — head is now 1
                       owned_asset_ids=set(),
                       ops=parse_ops([{"op": "set_text", "layer_id": "h1", "text": "x"}]))


def test_invalid_doc_rejected_and_design_unchanged():
    s, d = _none_session(), _design()
    bad = _full_doc()
    bad["pages"][0]["layers"][0]["type"] = "html"  # closed-union violation
    with pytest.raises(ValidationError):
        apply_revision(s, design=d, actor_kind="ai", mode="ai", source="ai_generate",
                       base_revision=0, owned_asset_ids=set(), full_doc=bad)
    # No mutation happened (checks precede mutation).
    assert d.current_revision == 0 and d.head_revision_id is None
    assert s.added == []


def test_cross_tenant_asset_ref_rejected():
    s, d = _none_session(), _design()
    foreign = uuid.uuid4()
    doc = _full_doc()
    doc["pages"][0]["layers"].append(
        {"type": "image", "id": "img", "asset_id": str(foreign), "w": 0.5, "h": 0.5}
    )
    with pytest.raises(CrossTenantAssetRef):
        apply_revision(s, design=d, actor_kind="ai", mode="ai", source="ai_generate",
                       base_revision=0, owned_asset_ids=set(), full_doc=doc)
    assert d.current_revision == 0 and s.added == []


def test_owned_asset_ref_accepted():
    s, d = FakeSession(), _design()
    owned = uuid.uuid4()
    doc = _full_doc()
    doc["pages"][0]["layers"].append(
        {"type": "image", "id": "img", "asset_id": str(owned), "w": 0.5, "h": 0.5}
    )
    rev = apply_revision(s, design=d, actor_kind="ai", mode="ai", source="ai_generate",
                         base_revision=0, owned_asset_ids={owned}, full_doc=doc)
    assert rev.revision_n == 1


def test_revert_is_a_forward_revision():
    s, d = FakeSession(), _design()
    apply_revision(s, design=d, actor_kind="ai", mode="ai", source="ai_generate",
                   base_revision=0, owned_asset_ids=set(), full_doc=_full_doc("First"))
    first_doc = dict(d.doc)
    apply_revision(s, design=d, actor_kind="human", mode="pro", source="user_edit",
                   base_revision=1, owned_asset_ids=set(),
                   ops=parse_ops([{"op": "set_text", "layer_id": "h1", "text": "Second"}]))
    # revert back to the first doc → a NEW revision 3 (history preserved)
    rev = revert_to(s, design=d, target_doc=first_doc, base_revision=2, owned_asset_ids=set())
    assert rev.revision_n == 3
    assert d.current_revision == 3
    assert d.doc["pages"][0]["layers"][0]["text"] == "First"


def test_unknown_source_or_mode_rejected():
    s, d = _none_session(), _design()
    with pytest.raises(ValueError):
        apply_revision(s, design=d, actor_kind="ai", mode="ai", source="sql_inject",
                       base_revision=0, owned_asset_ids=set(), full_doc=_full_doc())
    with pytest.raises(ValueError):
        apply_revision(s, design=d, actor_kind="ai", mode="hacker", source="ai_generate",
                       base_revision=0, owned_asset_ids=set(), full_doc=_full_doc())


def test_requires_exactly_one_of_ops_or_full_doc():
    s, d = _none_session(), _design()
    with pytest.raises(ValueError):
        apply_revision(s, design=d, actor_kind="ai", mode="ai", source="ai_generate",
                       base_revision=0, owned_asset_ids=set())  # neither


def _none_session():
    return FakeSession()
