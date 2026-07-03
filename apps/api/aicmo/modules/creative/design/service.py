"""Creative Studio design service — orchestrates the ONE write path.

Every mutating operation funnels through `revision.apply_revision`
(Law 3). AI-authored revisions (generate/edit/transform/restyle) are
metered (as `generation`) + audited; human Pro-mode edits are recorded by
the immutable revision row itself. Transforms/restyles produce a NEW design
(derive, never mutate the source).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.ai_audit import service as ai_audit
from aicmo.modules.billing import billing_live
from aicmo.modules.creative.design import ai_router, image_providers, transform
from aicmo.modules.creative.design.image_providers import ImageGenRequest
from aicmo.modules.creative.design.layer_schema import assert_tenant_refs, validate_doc
from aicmo.modules.creative.design.models import (
    BrandAsset,
    CreativeDesign,
    CreativeDesignRevision,
)
from aicmo.modules.creative.design.ops import apply_ops, parse_ops
from aicmo.modules.creative.design.revision import (
    apply_revision,
    new_design,
    owned_asset_ids,
    revert_to,
)
from aicmo.modules.creative.design.schemas import (
    BrandAssetCreate,
    CreateDesignRequest,
    RestyleRequest,
    TransformRequest,
)
from aicmo.modules.creative.models import CreativeCostEvent
from aicmo.modules.creative.storage.base import StorageRef
from aicmo.modules.creative.storage.registry import get_storage_backend
from aicmo.tenancy.context import TenantContext


class MissingBrand(ValueError):
    """A brand-scoped design op was requested without a resolved brand."""


def _brand_id(tenant: TenantContext) -> uuid.UUID:
    if tenant.brand_id is None:
        raise MissingBrand("a brand is required for design operations")
    return tenant.brand_id


async def _meter_and_audit(
    session: AsyncSession, *, tenant: TenantContext, source: str, design_id: uuid.UUID
) -> None:
    """AI-authored revision: soft-gate quota, record usage, write audit.
    All best-effort / fail-open (never blocks the studio)."""
    await billing_live.enforce_quota(
        session, organization_id=tenant.organization_id, kind="generation"
    )
    await billing_live.record_metered(
        session, organization_id=tenant.organization_id, kind="generation",
        user_id=tenant.user_uuid, brand_id=tenant.brand_id,
        metadata={"feature": "creative_studio", "source": source},
    )
    await ai_audit.record_ai_generation(
        session, tenant=tenant, action_type=f"design.{source}", asset_id=design_id,
        metadata={"source": source},
    )


# ---------------------------------------------------------------------
#  AI Mode — create a design (revision 1)
# ---------------------------------------------------------------------
async def create_design(
    session: AsyncSession, *, tenant: TenantContext, payload: CreateDesignRequest
) -> CreativeDesign:
    brand_id = _brand_id(tenant)
    design = new_design(
        organization_id=tenant.organization_id, brand_id=brand_id, user_id=tenant.user_id,
        name=payload.name, media_type=payload.media_type, format_slug=payload.format_slug,
        creative_project_id=payload.creative_project_id,
        growth_objective_id=payload.growth_objective_id, default_mode="ai",
    )
    session.add(design)
    full_doc = transform.stub_compose(
        format_slug=payload.format_slug, headline=payload.headline,
        subhead=payload.subhead, cta=payload.cta,
    )
    owned = await owned_asset_ids(session, organization_id=tenant.organization_id)
    apply_revision(
        session, design=design, actor_kind="ai", mode="ai", source="ai_generate",
        base_revision=0, owned_asset_ids=owned, full_doc=full_doc,
        edit_summary="AI generated",
    )
    await _meter_and_audit(session, tenant=tenant, source="ai_generate", design_id=design.id)
    return design


async def create_design_from_doc(
    session: AsyncSession, *, tenant: TenantContext, name: str, media_type: str,
    full_doc: dict, format_slug: str | None = None,
    growth_objective_id: uuid.UUID | None = None,
    creative_project_id: uuid.UUID | None = None,
    edit_summary: str = "AI generated", meter: bool = True,
) -> CreativeDesign:
    """Persist a pre-composed LayerDoc as a new design (AI Mode, revision 1).
    Used by the campaign orchestrator — same write path + validation as every
    other create. `meter=False` lets a batch meter once for the whole campaign."""
    brand_id = _brand_id(tenant)
    design = new_design(
        organization_id=tenant.organization_id, brand_id=brand_id, user_id=tenant.user_id,
        name=name, media_type=media_type, format_slug=format_slug,
        creative_project_id=creative_project_id, growth_objective_id=growth_objective_id,
        default_mode="ai",
    )
    session.add(design)
    owned = await owned_asset_ids(session, organization_id=tenant.organization_id)
    apply_revision(
        session, design=design, actor_kind="ai", mode="ai", source="ai_generate",
        base_revision=0, owned_asset_ids=owned, full_doc=full_doc, edit_summary=edit_summary,
    )
    if meter:
        await _meter_and_audit(session, tenant=tenant, source="ai_generate", design_id=design.id)
    return design


# ---------------------------------------------------------------------
#  Reads
# ---------------------------------------------------------------------
async def get_design(
    session: AsyncSession, *, tenant: TenantContext, design_id: uuid.UUID
) -> CreativeDesign | None:
    brand_id = _brand_id(tenant)
    return await session.scalar(
        select(CreativeDesign).where(
            CreativeDesign.id == design_id, CreativeDesign.brand_id == brand_id
        )
    )


async def list_designs(
    session: AsyncSession, *, tenant: TenantContext
) -> list[CreativeDesign]:
    brand_id = _brand_id(tenant)
    rows = await session.execute(
        select(CreativeDesign)
        .where(CreativeDesign.brand_id == brand_id)
        .order_by(CreativeDesign.updated_at.desc())
    )
    return list(rows.scalars().all())


async def list_revisions(
    session: AsyncSession, *, tenant: TenantContext, design: CreativeDesign
) -> list[CreativeDesignRevision]:
    rows = await session.execute(
        select(CreativeDesignRevision)
        .where(CreativeDesignRevision.design_id == design.id)
        .order_by(CreativeDesignRevision.revision_n.asc())
    )
    return list(rows.scalars().all())


# ---------------------------------------------------------------------
#  Guided Mode — AI edit (NL → op-class → ops)
# ---------------------------------------------------------------------
async def ai_edit(
    session: AsyncSession, *, tenant: TenantContext, design: CreativeDesign,
    instruction: str, base_revision: int,
) -> CreativeDesign:
    op_class = ai_router.classify(instruction)
    owned = await owned_asset_ids(session, organization_id=tenant.organization_id)
    if op_class == "edit":
        ops = parse_ops(ai_router.stub_edit_ops(design.doc, instruction))
        apply_revision(
            session, design=design, actor_kind="ai", mode="guided", source="ai_edit",
            base_revision=base_revision, owned_asset_ids=owned, ops=ops,
            edit_summary=instruction[:120],
        )
        await _meter_and_audit(session, tenant=tenant, source="ai_edit", design_id=design.id)
    else:  # regenerate/transform/restyle dispatched via the editor for CS1 → treat as edit
        ops = parse_ops(ai_router.stub_edit_ops(design.doc, instruction))
        apply_revision(
            session, design=design, actor_kind="ai", mode="guided", source="ai_regenerate",
            base_revision=base_revision, owned_asset_ids=owned, ops=ops,
            edit_summary=instruction[:120],
        )
        await _meter_and_audit(session, tenant=tenant, source="ai_regenerate", design_id=design.id)
    return design


# ---------------------------------------------------------------------
#  Pro Mode — human edit (ops or full doc). Same write path; no AI meter.
# ---------------------------------------------------------------------
async def pro_edit(
    session: AsyncSession, *, tenant: TenantContext, design: CreativeDesign,
    base_revision: int, ops: list[dict] | None, full_doc: dict | None,
) -> CreativeDesign:
    owned = await owned_asset_ids(session, organization_id=tenant.organization_id)
    typed_ops = parse_ops(ops) if ops is not None else None
    apply_revision(
        session, design=design, actor_kind="human", mode="pro", source="user_edit",
        base_revision=base_revision, owned_asset_ids=owned, ops=typed_ops,
        full_doc=full_doc, created_by_user_id=tenant.user_id, edit_summary="Edited",
    )
    return design


# ---------------------------------------------------------------------
#  Revert — itself a forward revision (never a destructive rewind)
# ---------------------------------------------------------------------
async def revert(
    session: AsyncSession, *, tenant: TenantContext, design: CreativeDesign,
    target_revision: int, base_revision: int,
) -> CreativeDesign:
    target = await session.scalar(
        select(CreativeDesignRevision).where(
            CreativeDesignRevision.design_id == design.id,
            CreativeDesignRevision.revision_n == target_revision,
        )
    )
    if target is None:
        raise ValueError("target revision not found")
    owned = await owned_asset_ids(session, organization_id=tenant.organization_id)
    revert_to(
        session, design=design, target_doc=target.doc, base_revision=base_revision,
        owned_asset_ids=owned, created_by_user_id=tenant.user_id,
    )
    return design


# ---------------------------------------------------------------------
#  Transform / Restyle — produce a NEW design (derive, never mutate)
# ---------------------------------------------------------------------
async def transform_design(
    session: AsyncSession, *, tenant: TenantContext, source: CreativeDesign,
    payload: TransformRequest, target_aspect: str | None = None,
) -> CreativeDesign:
    brand_id = _brand_id(tenant)
    new_doc = transform.stub_transform_doc(source.doc, payload.kind, payload.target_format_slug)
    if target_aspect:
        new_doc["aspect"] = target_aspect
    derived = new_design(
        organization_id=tenant.organization_id, brand_id=brand_id, user_id=tenant.user_id,
        name=f"{source.name} ({payload.kind})", media_type=source.media_type,
        format_slug=payload.target_format_slug or source.format_slug,
        growth_objective_id=source.growth_objective_id, default_mode="ai",
    )
    session.add(derived)
    owned = await owned_asset_ids(session, organization_id=tenant.organization_id)
    apply_revision(
        session, design=derived, actor_kind="ai", mode="guided", source="ai_transform",
        base_revision=0, owned_asset_ids=owned, full_doc=new_doc,
        edit_summary=f"Transform: {payload.kind}",
    )
    await _meter_and_audit(session, tenant=tenant, source="ai_transform", design_id=derived.id)
    return derived


async def restyle_design(
    session: AsyncSession, *, tenant: TenantContext, source: CreativeDesign,
    payload: RestyleRequest,
) -> CreativeDesign:
    brand_id = _brand_id(tenant)
    new_doc = transform.stub_restyle_doc(source.doc, payload.style)
    derived = new_design(
        organization_id=tenant.organization_id, brand_id=brand_id, user_id=tenant.user_id,
        name=f"{source.name} ({payload.style})", media_type=source.media_type,
        format_slug=source.format_slug, growth_objective_id=source.growth_objective_id,
        default_mode="ai",
    )
    session.add(derived)
    owned = await owned_asset_ids(session, organization_id=tenant.organization_id)
    apply_revision(
        session, design=derived, actor_kind="ai", mode="guided", source="ai_restyle",
        base_revision=0, owned_asset_ids=owned, full_doc=new_doc,
        edit_summary=f"Restyle: {payload.style}",
    )
    await _meter_and_audit(session, tenant=tenant, source="ai_restyle", design_id=derived.id)
    return derived


async def generate_variants(
    session: AsyncSession, *, tenant: TenantContext, source: CreativeDesign, count: int
) -> list[CreativeDesign]:
    """Fork the source design into N independent variants — each its own
    editable design + history (a branching primitive). The user diverges them
    via further NL/Pro edits; richer per-variable A/B is a later refinement."""
    out: list[CreativeDesign] = []
    for k in range(max(1, min(count, 8))):
        derived = await create_design_from_doc(
            session, tenant=tenant, name=f"{source.name} · variant {k + 1}",
            media_type=source.media_type, full_doc=source.doc,
            format_slug=source.format_slug, growth_objective_id=source.growth_objective_id,
            edit_summary=f"Variant {k + 1}", meter=True,
        )
        out.append(derived)
    return out


class NlEditOutcome:
    """Result of an NL edit — what happened, with confidence + (for preview)
    the proposed doc, or (for create-ops) the new designs."""

    __slots__ = (
        "committed",
        "confidence",
        "created_designs",
        "design",
        "notes",
        "op_class",
        "proposed_doc",
        "summary",
    )

    def __init__(self, *, op_class, confidence, summary, committed, design,
                 proposed_doc=None, created_designs=None, notes=None) -> None:
        self.op_class = op_class
        self.confidence = confidence
        self.summary = summary
        self.committed = committed
        self.design = design
        self.proposed_doc = proposed_doc
        self.created_designs = created_designs or []
        self.notes = notes


async def nl_edit(
    session: AsyncSession, *, tenant: TenantContext, design: CreativeDesign,
    instruction: str, base_revision: int, preview: bool,
) -> NlEditOutcome:
    """The unified NL editor. Plans the instruction with the LLM (fallback when
    unavailable) and routes it: edit/regenerate revise the design in place via
    apply_revision; restyle/transform/variant produce new designs. `preview`
    computes the result WITHOUT writing a revision (nothing mutates)."""
    # ---- AI image replace ("replace this person with a female doctor") ----
    img_layer = (
        ai_router.first_image_layer_id(design.doc, hint=instruction)
        if ai_router.is_image_replace(instruction) else None
    )
    if img_layer:
        prompt = ai_router.extract_replace_target(instruction)
        if preview:
            return NlEditOutcome(
                op_class="edit", confidence=70, committed=False, design=design,
                summary=f"Replace image with: {prompt}",
                notes="Apply to generate the new image and replace it (a new asset; the original is kept).",
            )
        new_asset = await generate_image_asset(session, tenant=tenant, prompt=prompt)
        await session.flush()  # so owned_asset_ids sees the new asset
        owned = await owned_asset_ids(session, organization_id=tenant.organization_id)
        typed = parse_ops([{"op": "replace_image", "layer_id": img_layer,
                            "asset_id": str(new_asset.id)}])
        apply_revision(
            session, design=design, actor_kind="ai", mode="guided", source="ai_edit",
            base_revision=base_revision, owned_asset_ids=owned, ops=typed,
            edit_summary=f"AI replace image: {prompt[:80]}",
        )
        await _meter_and_audit(session, tenant=tenant, source="ai_edit", design_id=design.id)
        return NlEditOutcome(op_class="edit", confidence=70, committed=True, design=design,
                             summary=f"Replaced image with: {prompt}")

    plan = await ai_router.plan_edit(instruction, design.doc)
    owned = await owned_asset_ids(session, organization_id=tenant.organization_id)

    def _outcome(**kw):
        return NlEditOutcome(op_class=plan.op_class, confidence=plan.confidence,
                             summary=plan.summary, notes=plan.notes, **kw)

    # ---- in-place edits (edit / regenerate) ----
    if plan.op_class in ("edit", "regenerate"):
        if not plan.ops:
            return _outcome(committed=False, design=design,
                            notes=plan.notes or "No applicable change.")
        typed = parse_ops(plan.ops)
        proposed = apply_ops(design.doc, typed)              # pure
        validated = validate_doc(proposed)                    # raises 422
        assert_tenant_refs(validated, owned)                  # raises 422
        if preview:
            return _outcome(committed=False, design=design,
                            proposed_doc=validated.model_dump(mode="json"))
        source = "ai_edit" if plan.op_class == "edit" else "ai_regenerate"
        apply_revision(
            session, design=design, actor_kind="ai", mode="guided", source=source,
            base_revision=base_revision, owned_asset_ids=owned, ops=typed,
            edit_summary=plan.summary,
        )
        await _meter_and_audit(session, tenant=tenant, source=source, design_id=design.id)
        return _outcome(committed=True, design=design)

    # ---- create-new ops (restyle / transform / variant) ----
    if preview:
        kind_note = {
            "restyle": f"Will create a restyled version: {plan.style or instruction}",
            "transform": f"Will create a {plan.transform_kind or 'reformatted'} design"
                         + (f" ({plan.target_aspect})" if plan.target_aspect else ""),
            "variant": f"Will create {plan.variant_count or 3} variants",
        }[plan.op_class]
        return _outcome(committed=False, design=design, notes=kind_note)

    if plan.op_class == "restyle":
        new = await restyle_design(
            session, tenant=tenant, source=design,
            payload=RestyleRequest(style=(plan.style or instruction[:80]),
                                   base_revision=design.current_revision),
        )
        return _outcome(committed=True, design=design, created_designs=[new])
    if plan.op_class == "transform":
        new = await transform_design(
            session, tenant=tenant, source=design,
            payload=TransformRequest(kind=plan.transform_kind or "reformat",
                                     base_revision=design.current_revision),
            target_aspect=plan.target_aspect,
        )
        return _outcome(committed=True, design=design, created_designs=[new])
    # variant
    news = await generate_variants(session, tenant=tenant, source=design,
                                   count=plan.variant_count or 3)
    return _outcome(committed=True, design=design, created_designs=news)


# ---------------------------------------------------------------------
#  Brand assets (tenant-owned uploads the layer doc references)
# ---------------------------------------------------------------------
async def create_brand_asset(
    session: AsyncSession, *, tenant: TenantContext, payload: BrandAssetCreate
) -> BrandAsset:
    brand_id = _brand_id(tenant)
    asset = BrandAsset(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=brand_id,
        user_id=tenant.user_id, kind=payload.kind, label=payload.label,
        storage_backend=payload.storage_backend, storage_key=payload.storage_key,
        mime_type=payload.mime_type, meta=payload.meta,
    )
    session.add(asset)
    return asset


async def upload_brand_asset(
    session: AsyncSession, *, tenant: TenantContext, kind: str, data: bytes,
    content_type: str, label: str | None = None, meta: dict | None = None,
) -> BrandAsset:
    """Store an uploaded file in the active storage backend + register a
    tenant-owned brand_asset pointing at it (StorageRef, never bytes in PG).

    `meta` carries provenance (e.g. the AI-generation contract) into the
    asset's JSONB — persisted, queryable, never fabricated."""
    brand_id = _brand_id(tenant)
    backend = get_storage_backend()
    key = f"brand_asset/{tenant.organization_id}/{uuid.uuid4().hex}"
    ref = backend.put(key=key, data=data, content_type=content_type or "application/octet-stream")
    asset = BrandAsset(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=brand_id,
        user_id=tenant.user_id, kind=kind, label=label,
        storage_backend=ref.backend, storage_key=ref.key, mime_type=content_type,
        meta=meta or {},
    )
    session.add(asset)
    return asset


async def list_brand_assets(
    session: AsyncSession, *, tenant: TenantContext, kind: str | None = None,
    query: str | None = None, favorites_only: bool = False,
) -> list[BrandAsset]:
    brand_id = _brand_id(tenant)
    stmt = select(BrandAsset).where(BrandAsset.brand_id == brand_id)
    if kind:
        stmt = stmt.where(BrandAsset.kind == kind)
    if favorites_only:
        stmt = stmt.where(BrandAsset.is_favorite.is_(True))
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(BrandAsset.label.ilike(like))
    stmt = stmt.order_by(BrandAsset.is_favorite.desc(), BrandAsset.created_at.desc())
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def toggle_favorite(
    session: AsyncSession, *, tenant: TenantContext, asset_id: uuid.UUID
) -> BrandAsset | None:
    brand_id = _brand_id(tenant)
    asset = await session.scalar(
        select(BrandAsset).where(BrandAsset.id == asset_id, BrandAsset.brand_id == brand_id)
    )
    if asset is None:
        return None
    asset.is_favorite = not asset.is_favorite
    return asset


def asset_signed_url(asset: BrandAsset) -> str | None:
    """A short-lived signed URL the canvas can render. None if no stored file."""
    if not asset.storage_backend or not asset.storage_key:
        return None
    ref = StorageRef(backend=asset.storage_backend, key=asset.storage_key)
    return get_storage_backend().signed_url(ref)


async def _load_asset(
    session: AsyncSession, *, tenant: TenantContext, asset_id: uuid.UUID
) -> BrandAsset | None:
    brand_id = _brand_id(tenant)
    return await session.scalar(
        select(BrandAsset).where(BrandAsset.id == asset_id, BrandAsset.brand_id == brand_id)
    )


async def remove_bg(
    session: AsyncSession, *, tenant: TenantContext, asset_id: uuid.UUID
) -> BrandAsset | None:
    """Background removal → a NEW transparent asset (original preserved). The
    editor then emits a replace_image op pointing the layer at the new asset."""
    src = await _load_asset(session, tenant=tenant, asset_id=asset_id)
    if src is None:
        return None
    data = b""
    backend = get_storage_backend()
    read = getattr(backend, "read", None)
    if read and src.storage_backend and src.storage_key:
        try:
            data = read(StorageRef(backend=src.storage_backend, key=src.storage_key))
        except Exception:
            data = b""
    new_bytes, mime = image_providers.get_bg_removal_provider().remove(
        data, src.mime_type or "image/png"
    )
    return await upload_brand_asset(
        session, tenant=tenant, kind="image", data=new_bytes, content_type=mime,
        label=f"{src.label or 'image'} (no bg)",
    )


async def generate_image_asset(
    session: AsyncSession, *, tenant: TenantContext, prompt: str, aspect: str = "1:1",
    negative_prompt: str | None = None, style: str | None = None,
    width: int | None = None, height: int | None = None, seed: int | None = None,
) -> BrandAsset:
    """AI text→image → a NEW asset (used by NL 'replace this with …' + the
    campaign composer's hero images). Real OpenAI image when a key is set.

    Persists the FULL generation contract (spec #2) into the asset's meta —
    prompt / negative_prompt / aspect / style / dimensions / seed / provider /
    model / cost / time — and records a creative_cost_event on the ledger."""
    result = await image_providers.get_image_gen_provider().generate(
        ImageGenRequest(
            prompt=prompt, negative_prompt=negative_prompt, aspect=aspect,
            style=style, width=width, height=height, seed=seed,
        )
    )
    generation = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "aspect_ratio": aspect,
        "style": style,
        "width": result.width,
        "height": result.height,
        "seed": result.seed,
        "provider": result.provider,
        "model": result.model,
        "generation_cost_cents": result.cost_cents,
        "generation_time_ms": result.duration_ms,
    }
    asset = await upload_brand_asset(
        session, tenant=tenant, kind="image", data=result.image_bytes,
        content_type=result.mime, label=f"AI: {prompt[:40]}",
        meta={"generation": generation},
    )
    session.add(
        CreativeCostEvent(
            id=uuid.uuid4(), organization_id=tenant.organization_id,
            brand_id=_brand_id(tenant), media_type="image", stage="image_generate",
            provider=result.provider, units=1, cost_cents=result.cost_cents,
            duration_ms=result.duration_ms,
        )
    )
    return asset


async def stock_search(query: str, *, limit: int = 12):
    """Stock provider search (stub → []). Real provider drops in later."""
    return await image_providers.get_stock_provider().search(query, limit=limit)
