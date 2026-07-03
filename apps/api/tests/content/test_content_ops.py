"""Phase 6.2B — enterprise content-ops (review workflow, versions, ownership)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from aicmo.modules.content import ops_service


# --------------------------------------------------------------------------
#  Review lifecycle (pure transition table)
# --------------------------------------------------------------------------
def test_lifecycle_allows_the_happy_path():
    a = ops_service._ALLOWED
    assert "in_review" in a["draft"]
    assert "approved" in a["in_review"]
    assert "published" in a["approved"]
    assert "archived" in a["published"]
    # and disallows illegal jumps
    assert "approved" not in a["draft"]        # can't approve without review
    assert "published" not in a["in_review"]   # must be approved first


def test_all_statuses_covered():
    for s in ops_service.REVIEW_STATUSES:
        assert s in ops_service._ALLOWED  # every status has an outbound rule


# --------------------------------------------------------------------------
#  transition_review — tenant-scoped + lifecycle-enforced + audited
# --------------------------------------------------------------------------
_BRAND = uuid.uuid4()
_TENANT = SimpleNamespace(
    brand_id=_BRAND, organization_id=uuid.uuid4(), user_id="u", user_uuid=uuid.uuid4()
)


def _content(status="draft", brand=_BRAND):
    return SimpleNamespace(
        id=uuid.uuid4(), brand_id=brand, organization_id=uuid.uuid4(),
        review_status=status,
    )


class _Session:
    def __init__(self, content):
        self._content = content
        self.added: list = []

    async def get(self, model, _id):
        return self._content if getattr(model, "__tablename__", "") == "generated_content" else None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass


@pytest.mark.asyncio
async def test_allowed_transition_updates_status_and_logs_event():
    content = _content("draft")
    session = _Session(content)
    out = await ops_service.transition_review(
        session, tenant=_TENANT, content_id=content.id, to_status="in_review", reason="ready"
    )
    assert out.review_status == "in_review"
    # a ContentReviewEvent was staged (plus an audit row)
    assert any(type(o).__name__ == "ContentReviewEvent" for o in session.added)
    ev = next(o for o in session.added if type(o).__name__ == "ContentReviewEvent")
    assert ev.from_status == "draft" and ev.to_status == "in_review"


@pytest.mark.asyncio
async def test_disallowed_transition_rejected_409():
    content = _content("draft")
    with pytest.raises(HTTPException) as ei:
        await ops_service.transition_review(
            _Session(content), tenant=_TENANT, content_id=content.id,
            to_status="published", reason=None,
        )
    assert ei.value.status_code == 409


@pytest.mark.asyncio
async def test_cross_tenant_content_rejected_404():
    other = _content("draft", brand=uuid.uuid4())  # different brand
    with pytest.raises(HTTPException) as ei:
        await ops_service.transition_review(
            _Session(other), tenant=_TENANT, content_id=other.id,
            to_status="in_review", reason=None,
        )
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_unknown_status_rejected_400():
    content = _content("draft")
    with pytest.raises(HTTPException) as ei:
        await ops_service.transition_review(
            _Session(content), tenant=_TENANT, content_id=content.id,
            to_status="bogus", reason=None,
        )
    assert ei.value.status_code == 400


# --------------------------------------------------------------------------
#  snapshot_version — computes next version number + carries source/author
# --------------------------------------------------------------------------
class _VersionSession:
    def __init__(self, max_no):
        self._max = max_no
        self.added: list = []

    async def execute(self, _stmt):
        return SimpleNamespace(scalar_one=lambda: self._max)

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_snapshot_increments_version_number():
    content = SimpleNamespace(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), brand_id=_BRAND,
        output={"a": 1}, strategy={"s": 1},
    )
    session = _VersionSession(max_no=2)  # existing max = 2 → next = 3
    v = await ops_service.snapshot_version(
        session, tenant=_TENANT, content=content, edit_source="manual", change_summary="edit"
    )
    assert v.version_no == 3
    assert v.edit_source == "manual"
    assert v.author_user_id == "u"
    assert v.output == {"a": 1}
