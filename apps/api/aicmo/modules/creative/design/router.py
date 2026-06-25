"""Creative Studio design HTTP surface (CS1).

Flag-gated behind `studio_enabled` (default false → 409), so the editable
design model ships dark. Every mutating route funnels through the design
service → `apply_revision` (Law 3). `mode` is a parameter of the route's
purpose, never a separate code path: ai-edit = Guided, PUT = Pro, create =
AI. Errors map uniformly: stale base → 409, schema/op violation → 422.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Request

from aicmo.config import get_settings
from aicmo.db.session import get_db
from aicmo.queue.deps import get_arq_pool
from aicmo.queue.enqueue import enqueue_tenant_job
from aicmo.modules.creative.design import service as design_service
from aicmo.modules.creative.design import video as video_orch
from aicmo.modules.creative.design.image_providers import StockResult
from aicmo.modules.creative.design.layer_schema import CrossTenantAssetRef
from aicmo.modules.creative.design.ops import OpError
from aicmo.modules.creative.design.revision import StaleRevision
from aicmo.modules.creative.design.schemas import (
    AiEditRequest,
    BrandAssetCreate,
    BrandAssetList,
    BrandAssetResponse,
    CreateDesignRequest,
    DesignList,
    DesignResponse,
    DesignSummary,
    ExportItem,
    ExportList,
    ExportRequest,
    NlEditRequest,
    NlEditResponse,
    ProEditRequest,
    VideoRenderResponse,
    VideoStatusResponse,
    RestyleRequest,
    RevertRequest,
    RevisionList,
    RevisionSummary,
    TransformRequest,
)
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/creative", tags=["creative-studio"])

_RequireRead = require_permission("content.read")
_RequireCreate = require_permission("content.create")


def _require_enabled() -> None:
    if not get_settings().studio_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="The Creative Studio isn't enabled yet."
        )


def _require_video() -> None:
    """Video rendering is additionally gated by video_enabled (it can spend)."""
    if not get_settings().video_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Video rendering isn't enabled yet."
        )


def _map_write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, StaleRevision):
        return HTTPException(status.HTTP_409_CONFLICT,
                             detail="This design changed since you loaded it. Reload and retry.")
    if isinstance(exc, (ValidationError, CrossTenantAssetRef, OpError)):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)[:300])
    if isinstance(exc, design_service.MissingBrand):
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select a brand first.")
    raise exc


async def _load(session: AsyncSession, tenant: TenantContext, design_id: uuid.UUID):
    design = await design_service.get_design(session, tenant=tenant, design_id=design_id)
    if design is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Design not found.")
    return design


# ---------------------------------------------------------------------
#  Designs
# ---------------------------------------------------------------------
@router.post("/designs", response_model=DesignResponse, status_code=status.HTTP_201_CREATED)
async def create_design(
    payload: CreateDesignRequest,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> DesignResponse:
    _require_enabled()
    try:
        design = await design_service.create_design(session, tenant=tenant, payload=payload)
    except Exception as exc:  # noqa: BLE001
        raise _map_write_error(exc)
    await session.commit()
    return DesignResponse.model_validate(design)


@router.get("/designs", response_model=DesignList)
async def list_designs(
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> DesignList:
    _require_enabled()
    rows = await design_service.list_designs(session, tenant=tenant)
    return DesignList(items=[DesignSummary.model_validate(r) for r in rows])


@router.get("/designs/{design_id}", response_model=DesignResponse)
async def get_design(
    design_id: uuid.UUID,
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> DesignResponse:
    _require_enabled()
    return DesignResponse.model_validate(await _load(session, tenant, design_id))


@router.get("/designs/{design_id}/revisions", response_model=RevisionList)
async def list_revisions(
    design_id: uuid.UUID,
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> RevisionList:
    _require_enabled()
    design = await _load(session, tenant, design_id)
    rows = await design_service.list_revisions(session, tenant=tenant, design=design)
    return RevisionList(items=[RevisionSummary.model_validate(r) for r in rows])


# ---------------------------------------------------------------------
#  Guided Mode — AI edit
# ---------------------------------------------------------------------
@router.post("/designs/{design_id}/ai-edit", response_model=DesignResponse)
async def ai_edit(
    design_id: uuid.UUID,
    payload: AiEditRequest,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> DesignResponse:
    _require_enabled()
    design = await _load(session, tenant, design_id)
    try:
        await design_service.ai_edit(
            session, tenant=tenant, design=design,
            instruction=payload.instruction, base_revision=payload.base_revision,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_write_error(exc)
    await session.commit()
    return DesignResponse.model_validate(design)


@router.post("/designs/{design_id}/nl-edit", response_model=NlEditResponse)
async def nl_edit(
    design_id: uuid.UUID,
    payload: NlEditRequest,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> NlEditResponse:
    """Modify a creative entirely through natural language. The router decides
    edit / regenerate / transform / restyle / variant, scores its confidence,
    and (preview=false) commits via apply_revision — full history preserved."""
    _require_enabled()
    design = await _load(session, tenant, design_id)
    try:
        outcome = await design_service.nl_edit(
            session, tenant=tenant, design=design, instruction=payload.instruction,
            base_revision=payload.base_revision, preview=payload.preview,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_write_error(exc)
    if outcome.committed:
        await session.commit()
    return NlEditResponse(
        op_class=outcome.op_class, confidence=outcome.confidence, summary=outcome.summary,
        committed=outcome.committed, design_id=outcome.design.id,
        current_revision=outcome.design.current_revision, proposed_doc=outcome.proposed_doc,
        created_design_ids=[d.id for d in outcome.created_designs], notes=outcome.notes,
    )


# ---------------------------------------------------------------------
#  Pro Mode — human edit (ops or full doc)
# ---------------------------------------------------------------------
@router.put("/designs/{design_id}", response_model=DesignResponse)
async def pro_edit(
    design_id: uuid.UUID,
    payload: ProEditRequest,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> DesignResponse:
    _require_enabled()
    if (payload.ops is None) == (payload.doc is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Provide exactly one of ops or doc.")
    design = await _load(session, tenant, design_id)
    try:
        await design_service.pro_edit(
            session, tenant=tenant, design=design, base_revision=payload.base_revision,
            ops=payload.ops, full_doc=payload.doc,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_write_error(exc)
    await session.commit()
    return DesignResponse.model_validate(design)


# ---------------------------------------------------------------------
#  Revert / Transform / Restyle
# ---------------------------------------------------------------------
@router.post("/designs/{design_id}/revert", response_model=DesignResponse)
async def revert(
    design_id: uuid.UUID,
    payload: RevertRequest,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> DesignResponse:
    _require_enabled()
    design = await _load(session, tenant, design_id)
    try:
        await design_service.revert(
            session, tenant=tenant, design=design,
            target_revision=payload.target_revision, base_revision=payload.base_revision,
        )
    except ValueError as exc:
        if isinstance(exc, (StaleRevision,)):
            raise _map_write_error(exc)
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Target revision not found.")
    await session.commit()
    return DesignResponse.model_validate(design)


@router.post("/designs/{design_id}/transform", response_model=DesignResponse,
             status_code=status.HTTP_201_CREATED)
async def transform_design(
    design_id: uuid.UUID,
    payload: TransformRequest,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> DesignResponse:
    _require_enabled()
    source = await _load(session, tenant, design_id)
    try:
        derived = await design_service.transform_design(
            session, tenant=tenant, source=source, payload=payload
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_write_error(exc)
    await session.commit()
    return DesignResponse.model_validate(derived)


@router.post("/designs/{design_id}/restyle", response_model=DesignResponse,
             status_code=status.HTTP_201_CREATED)
async def restyle_design(
    design_id: uuid.UUID,
    payload: RestyleRequest,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> DesignResponse:
    _require_enabled()
    source = await _load(session, tenant, design_id)
    try:
        derived = await design_service.restyle_design(
            session, tenant=tenant, source=source, payload=payload
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_write_error(exc)
    await session.commit()
    return DesignResponse.model_validate(derived)


# ---------------------------------------------------------------------
#  Brand assets — the asset library (logos/product/team/icons/illustrations)
# ---------------------------------------------------------------------
def _asset_out(asset) -> BrandAssetResponse:
    out = BrandAssetResponse.model_validate(asset)
    out.url = design_service.asset_signed_url(asset)
    return out


@router.post("/brand-assets", response_model=BrandAssetResponse, status_code=status.HTTP_201_CREATED)
async def create_brand_asset(
    payload: BrandAssetCreate,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> BrandAssetResponse:
    _require_enabled()
    try:
        asset = await design_service.create_brand_asset(session, tenant=tenant, payload=payload)
    except design_service.MissingBrand:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select a brand first.")
    await session.commit()
    return _asset_out(asset)


@router.post("/brand-assets/upload", response_model=BrandAssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_brand_asset(
    kind: str = Form("image"),
    label: str | None = Form(None),
    file: UploadFile = File(...),
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> BrandAssetResponse:
    _require_enabled()
    if kind not in ("logo", "font", "image", "color", "icon"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid asset kind.")
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty file.")
    try:
        asset = await design_service.upload_brand_asset(
            session, tenant=tenant, kind=kind, data=data,
            content_type=file.content_type or "application/octet-stream",
            label=label or file.filename,
        )
    except design_service.MissingBrand:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select a brand first.")
    await session.commit()
    return _asset_out(asset)


@router.get("/brand-assets", response_model=BrandAssetList)
async def list_brand_assets(
    kind: str | None = None,
    q: str | None = None,
    favorites: bool = False,
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> BrandAssetList:
    _require_enabled()
    rows = await design_service.list_brand_assets(
        session, tenant=tenant, kind=kind, query=q, favorites_only=favorites
    )
    return BrandAssetList(items=[_asset_out(r) for r in rows])


@router.post("/brand-assets/{asset_id}/favorite", response_model=BrandAssetResponse)
async def favorite_brand_asset(
    asset_id: uuid.UUID,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> BrandAssetResponse:
    _require_enabled()
    asset = await design_service.toggle_favorite(session, tenant=tenant, asset_id=asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Asset not found.")
    await session.commit()
    return _asset_out(asset)


@router.post("/brand-assets/{asset_id}/remove-bg", response_model=BrandAssetResponse,
             status_code=status.HTTP_201_CREATED)
async def remove_bg(
    asset_id: uuid.UUID,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> BrandAssetResponse:
    """Produce a NEW background-removed asset (original preserved). The editor
    then emits a replace_image op to point the layer at it (→ revision)."""
    _require_enabled()
    new_asset = await design_service.remove_bg(session, tenant=tenant, asset_id=asset_id)
    if new_asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Asset not found.")
    await session.commit()
    return _asset_out(new_asset)


@router.get("/brand-assets/stock", response_model=list[StockResult])
async def search_stock(
    q: str,
    _tenant: TenantContext = Depends(_RequireRead),
) -> list[StockResult]:
    """Stock provider search (abstraction; stub returns [] until a provider
    is wired)."""
    _require_enabled()
    return await design_service.stock_search(q)


# ---------------------------------------------------------------------
#  Video rendering (CS6) — reel/storyboard design → MP4 (async)
# ---------------------------------------------------------------------
@router.post("/designs/{design_id}/render-video", response_model=VideoRenderResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def render_video(
    design_id: uuid.UUID,
    request: Request,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
    pool=Depends(get_arq_pool),
) -> VideoRenderResponse:
    """Render an editable reel design into an MP4. Bridges to the video
    subsystem and enqueues an Arq job — the request never blocks on Veo."""
    _require_enabled()
    _require_video()
    design = await _load(session, tenant, design_id)
    try:
        project = await video_orch.start_render(session, tenant=tenant, design=design)
    except video_orch.OverDailyCap as e:
        await session.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Daily video limit reached ({e.cap}/day).")
    except video_orch.OverBudget:
        await session.commit()
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            detail="This would exceed your monthly creative budget.")
    await session.commit()
    await enqueue_tenant_job(pool, "render_design_video", str(project.id), tenant=tenant)
    return VideoRenderResponse(design_id=design.id, project_id=project.id, status=project.status)


@router.get("/designs/{design_id}/video", response_model=VideoStatusResponse)
async def video_status(
    design_id: uuid.UUID,
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> VideoStatusResponse:
    _require_enabled()
    design = await _load(session, tenant, design_id)
    st = await video_orch.get_video_status(session, tenant=tenant, design=design)
    project = st.get("project")
    return VideoStatusResponse(
        design_id=design.id,
        project_id=project.id if project else None,
        status=project.status if project else "none",
        asset_id=st.get("asset_id"), video_url=st.get("video_url"),
        captions_url=st.get("captions_url"), duration_ms=st.get("duration_ms"),
        scenes=st.get("scenes"),
    )


# ---------------------------------------------------------------------
#  Publishing exports (CS6) — per-platform re-targets of the rendered MP4
# ---------------------------------------------------------------------
@router.post("/assets/{asset_id}/exports", response_model=ExportList,
             status_code=status.HTTP_201_CREATED)
async def create_exports(
    asset_id: uuid.UUID,
    payload: ExportRequest,
    tenant: TenantContext = Depends(_RequireCreate),
    session: AsyncSession = Depends(get_db),
) -> ExportList:
    _require_enabled()
    exports = await video_orch.prepare_exports(
        session, tenant=tenant, asset_id=asset_id, platforms=payload.platforms
    )
    if exports is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Asset not found.")
    await session.commit()
    return ExportList(items=[ExportItem.model_validate(e) for e in exports])


@router.get("/assets/{asset_id}/exports", response_model=ExportList)
async def list_exports(
    asset_id: uuid.UUID,
    tenant: TenantContext = Depends(_RequireRead),
    session: AsyncSession = Depends(get_db),
) -> ExportList:
    _require_enabled()
    rows = await video_orch.list_exports(session, tenant=tenant, asset_id=asset_id)
    return ExportList(items=[ExportItem.model_validate(e) for e in rows])
