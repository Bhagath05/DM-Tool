"""The Revision Engine — `apply_revision`, the ONE write path (Law 3).

No code may mutate a design in place. Every change — AI Mode, Guided Mode,
or Pro Mode, full generation or one-pixel nudge — goes through
`apply_revision`, which:

  1. checks the optimistic lock (stale base → StaleRevision → 409),
  2. resolves the next doc (apply ops to the head, or take a full doc),
  3. validates it against the CLOSED layer schema (raises on any violation),
  4. asserts every asset ref is tenant-owned (no cross-tenant leakage),
  5. appends an immutable creative_design_revision (parent = old head),
  6. advances the head — the ONLY place design.doc / current_revision /
     head_revision_id are assigned.

This function is synchronous (it only does `session.add` + in-memory
mutation); the async service layer owns flush/commit and the surrounding
audit + metering. Keeping it sync makes the Law-3 invariant trivially
unit-testable.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.creative.design.layer_schema import (
    LayerDoc,
    assert_tenant_refs,
    validate_doc,
)
from aicmo.modules.creative.design.models import (
    BrandAsset,
    CreativeDesign,
    CreativeDesignRevision,
)
from aicmo.modules.creative.design.ops import EditOp, apply_ops
from aicmo.modules.creative.models import CreativeAsset

# Sources that count as AI-authored (for audit/metering branching).
AI_SOURCES = frozenset(
    {"ai_generate", "ai_edit", "ai_regenerate", "ai_restyle", "ai_transform"}
)
ALL_SOURCES = AI_SOURCES | {"user_edit", "template"}
MODES = frozenset({"ai", "guided", "pro"})


class StaleRevision(RuntimeError):
    """The caller's base_revision is not the current head → 409, rebase."""


def _empty_doc(format_slug: str | None) -> dict[str, Any]:
    doc = LayerDoc(format_slug=format_slug)
    return doc.model_dump(mode="json")


def new_design(
    *,
    organization_id: uuid.UUID,
    brand_id: uuid.UUID,
    name: str,
    media_type: str,
    format_slug: str | None = None,
    creative_project_id: uuid.UUID | None = None,
    growth_objective_id: uuid.UUID | None = None,
    default_mode: str = "ai",
    user_id: str | None = None,
) -> CreativeDesign:
    """Construct a fresh design at revision 0 (empty doc, no head). The first
    `apply_revision(base_revision=0, full_doc=...)` produces revision 1."""
    return CreativeDesign(
        id=uuid.uuid4(),
        organization_id=organization_id,
        brand_id=brand_id,
        user_id=user_id,
        creative_project_id=creative_project_id,
        growth_objective_id=growth_objective_id,
        format_slug=format_slug,
        name=name,
        media_type=media_type,
        doc=_empty_doc(format_slug),
        current_revision=0,
        head_revision_id=None,
        default_mode=default_mode,
        status="draft",
    )


async def owned_asset_ids(session: AsyncSession, *, organization_id: uuid.UUID) -> set[uuid.UUID]:
    """The set of asset ids the tenant owns (brand_asset + creative_asset).
    A design may only reference assets in this set."""
    ids: set[uuid.UUID] = set()
    for model in (BrandAsset, CreativeAsset):
        rows = await session.execute(
            select(model.id).where(model.organization_id == organization_id)
        )
        ids.update(rows.scalars().all())
    return ids


def apply_revision(
    session: AsyncSession,
    *,
    design: CreativeDesign,
    actor_kind: str,
    mode: str,
    source: str,
    base_revision: int,
    owned_asset_ids: set[uuid.UUID],
    ops: list[EditOp] | None = None,
    full_doc: dict[str, Any] | None = None,
    created_by_user_id: str | None = None,
    edit_summary: str | None = None,
) -> CreativeDesignRevision:
    """The single write path. Returns the new immutable revision and advances
    the design head. Raises StaleRevision / ValidationError / CrossTenantAssetRef
    — never partially mutates the design (all checks precede any mutation)."""
    if source not in ALL_SOURCES:
        raise ValueError(f"unknown revision source {source!r}")
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if actor_kind not in ("ai", "human"):
        raise ValueError(f"unknown actor_kind {actor_kind!r}")
    if (ops is None) == (full_doc is None):
        raise ValueError("provide exactly one of ops or full_doc")

    # 1. optimistic lock — checked BEFORE any mutation.
    if base_revision != design.current_revision:
        raise StaleRevision(
            f"base_revision {base_revision} != current {design.current_revision}"
        )

    # 2. resolve next doc.
    next_raw = apply_ops(design.doc, ops) if ops is not None else full_doc

    # 3. validate against the closed schema (raises ValidationError).
    validated = validate_doc(next_raw)
    validated_doc = validated.model_dump(mode="json")

    # 4. tenant-ownership of every asset ref (raises CrossTenantAssetRef).
    assert_tenant_refs(validated, owned_asset_ids)

    # 5. append the immutable revision (id generated up-front so we can set
    #    the head without a flush; parent = the OLD head → branch tree).
    rev_id = uuid.uuid4()
    rev = CreativeDesignRevision(
        id=rev_id,
        organization_id=design.organization_id,
        brand_id=design.brand_id,
        design_id=design.id,
        revision_n=design.current_revision + 1,
        parent_revision_id=design.head_revision_id,
        doc=validated_doc,
        ops=[o.model_dump(mode="json") for o in ops] if ops is not None else None,
        source=source,
        actor_kind=actor_kind,
        mode=mode,
        review_status="draft",
        created_by_user_id=created_by_user_id,
        edit_summary=edit_summary,
    )
    session.add(rev)

    # 6. advance head — the ONLY assignment to design.doc / current_revision /
    #    head_revision_id in the entire codebase.
    design.head_revision_id = rev_id
    design.doc = validated_doc
    design.current_revision = rev.revision_n
    return rev


def revert_to(
    session: AsyncSession,
    *,
    design: CreativeDesign,
    target_doc: dict[str, Any],
    base_revision: int,
    owned_asset_ids: set[uuid.UUID],
    actor_kind: str = "human",
    mode: str = "pro",
    created_by_user_id: str | None = None,
) -> CreativeDesignRevision:
    """Revert is itself a forward revision (you can undo an undo) — never a
    destructive rewind. The target doc becomes a new head."""
    return apply_revision(
        session,
        design=design,
        actor_kind=actor_kind,
        mode=mode,
        source="user_edit",
        base_revision=base_revision,
        owned_asset_ids=owned_asset_ids,
        full_doc=target_doc,
        created_by_user_id=created_by_user_id,
        edit_summary="revert",
    )
