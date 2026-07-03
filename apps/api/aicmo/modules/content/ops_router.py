"""Phase 6.2B — enterprise content-ops HTTP surface.

Mounted BEFORE the base content router so literal paths (/content/folders,
/content/search) resolve before /content/{content_id}. Every endpoint is
tenant-scoped (the service filters by brand) + RBAC-gated + audited.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.content import ops_service
from aicmo.modules.content.ops_schemas import (
    AssignFolderRequest,
    CommentCreate,
    CommentList,
    CommentResolveRequest,
    CommentResponse,
    ContentVersionList,
    ContentVersionResponse,
    EditRequest,
    FolderCreate,
    FolderList,
    FolderResponse,
    FolderUpdate,
    RestoreRequest,
    ReviewEventResponse,
    ReviewHistoryList,
    ReviewTransitionRequest,
    VersionCompare,
    VersionOutput,
)
from aicmo.modules.content.schemas import GeneratedContentResponse
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/content", tags=["content-ops"])

_VIEW = require_permission("library.view")
_EDIT = require_permission("content.edit")
_DELETE = require_permission("content.delete")


# ---------------------------------------------------------------------
#  Search (literal — before /{content_id})
# ---------------------------------------------------------------------
@router.get("/search")
async def search(
    q: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    folder_id: uuid.UUID | None = Query(default=None),
    campaign_id: uuid.UUID | None = Query(default=None),
    strategy_id: uuid.UUID | None = Query(default=None),
    saved_only: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(_VIEW),
) -> dict:
    rows, total = await ops_service.search_content(
        session, tenant=tenant, q=q, content_type=content_type,
        review_status=review_status, folder_id=folder_id, campaign_id=campaign_id,
        strategy_id=strategy_id, saved_only=saved_only, limit=limit, offset=offset,
    )
    return {
        "items": [GeneratedContentResponse.model_validate(r).model_dump(mode="json") for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------
#  Folders (literal — before /{content_id})
# ---------------------------------------------------------------------
@router.get("/folders", response_model=FolderList)
async def list_folders(
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW)
) -> FolderList:
    rows = await ops_service.list_folders(session, tenant=tenant)
    return FolderList(items=[FolderResponse.model_validate(r) for r in rows])


@router.post("/folders", response_model=FolderResponse, status_code=201)
async def create_folder(
    payload: FolderCreate,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(_EDIT),
) -> FolderResponse:
    row = await ops_service.create_folder(
        session, tenant=tenant, name=payload.name, kind=payload.kind,
        parent_id=payload.parent_id,
    )
    return FolderResponse.model_validate(row)


@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: uuid.UUID, payload: FolderUpdate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_EDIT),
) -> FolderResponse:
    row = await ops_service.update_folder(
        session, tenant=tenant, folder_id=folder_id, name=payload.name, pinned=payload.pinned,
    )
    return FolderResponse.model_validate(row)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_DELETE),
) -> None:
    await ops_service.delete_folder(session, tenant=tenant, folder_id=folder_id)


@router.post("/folders/assign")
async def assign_folder(
    payload: AssignFolderRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_EDIT),
) -> dict:
    moved = await ops_service.assign_to_folder(
        session, tenant=tenant, content_ids=payload.content_ids, folder_id=payload.folder_id,
    )
    return {"moved": moved}


# ---------------------------------------------------------------------
#  Comment resolve (literal 2-seg — before /{content_id})
# ---------------------------------------------------------------------
@router.patch("/comments/{comment_id}", response_model=CommentResponse)
async def resolve_comment(
    comment_id: uuid.UUID, payload: CommentResolveRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_EDIT),
) -> CommentResponse:
    row = await ops_service.set_comment_resolved(
        session, tenant=tenant, comment_id=comment_id, resolved=payload.resolved,
    )
    return CommentResponse.model_validate(row)


# ---------------------------------------------------------------------
#  Per-asset: versions / edit / review / comments
# ---------------------------------------------------------------------
@router.get("/{content_id}/versions", response_model=ContentVersionList)
async def list_versions(
    content_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> ContentVersionList:
    rows = await ops_service.list_versions(session, tenant=tenant, content_id=content_id)
    return ContentVersionList(items=[ContentVersionResponse.model_validate(r) for r in rows])


@router.get("/{content_id}/versions/compare", response_model=VersionCompare)
async def compare_versions(
    content_id: uuid.UUID,
    a: int = Query(..., ge=1),
    b: int = Query(..., ge=1),
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> VersionCompare:
    va = await ops_service.get_version(session, tenant=tenant, content_id=content_id, version_no=a)
    vb = await ops_service.get_version(session, tenant=tenant, content_id=content_id, version_no=b)
    return VersionCompare(
        a=VersionOutput(version_no=va.version_no, edit_source=va.edit_source, output=va.output),
        b=VersionOutput(version_no=vb.version_no, edit_source=vb.edit_source, output=vb.output),
    )


@router.post("/{content_id}/restore", response_model=GeneratedContentResponse)
async def restore(
    content_id: uuid.UUID, payload: RestoreRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_EDIT),
) -> GeneratedContentResponse:
    row = await ops_service.restore_version(
        session, tenant=tenant, content_id=content_id, version_no=payload.version_no,
    )
    return GeneratedContentResponse.model_validate(row)


@router.patch("/{content_id}/edit", response_model=GeneratedContentResponse)
async def edit(
    content_id: uuid.UUID, payload: EditRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_EDIT),
) -> GeneratedContentResponse:
    row = await ops_service.apply_edit(
        session, tenant=tenant, content_id=content_id, output=payload.output,
        change_summary=payload.change_summary,
    )
    return GeneratedContentResponse.model_validate(row)


@router.post("/{content_id}/review", response_model=GeneratedContentResponse)
async def review_transition(
    content_id: uuid.UUID, payload: ReviewTransitionRequest,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_EDIT),
) -> GeneratedContentResponse:
    row = await ops_service.transition_review(
        session, tenant=tenant, content_id=content_id, to_status=payload.to_status,
        reason=payload.reason,
    )
    return GeneratedContentResponse.model_validate(row)


@router.get("/{content_id}/review/history", response_model=ReviewHistoryList)
async def review_history(
    content_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> ReviewHistoryList:
    rows = await ops_service.review_history(session, tenant=tenant, content_id=content_id)
    return ReviewHistoryList(items=[ReviewEventResponse.model_validate(r) for r in rows])


@router.get("/{content_id}/comments", response_model=CommentList)
async def list_comments(
    content_id: uuid.UUID,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_VIEW),
) -> CommentList:
    rows = await ops_service.list_comments(session, tenant=tenant, content_id=content_id)
    return CommentList(items=[CommentResponse.model_validate(r) for r in rows])


@router.post("/{content_id}/comments", response_model=CommentResponse, status_code=201)
async def add_comment(
    content_id: uuid.UUID, payload: CommentCreate,
    session: AsyncSession = Depends(get_db), tenant: TenantContext = Depends(_EDIT),
) -> CommentResponse:
    row = await ops_service.add_comment(
        session, tenant=tenant, content_id=content_id, body=payload.body,
        parent_id=payload.parent_id, mentions=payload.mentions,
    )
    return CommentResponse.model_validate(row)
