"""Phase 6.2B — enterprise content-operations service.

Version history, folders/collections, threaded comments + mentions, and the
approval workflow — all over the EXISTING generated_content asset, all
tenant-scoped (every read/write filters by the caller's brand) and audited via
the reused audit service. Nothing here duplicates the Creative Studio design
pipeline.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import String, asc, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.audit import service as audit_service
from aicmo.modules.content.models import GeneratedContent
from aicmo.modules.content.ops_models import (
    ContentComment,
    ContentFolder,
    ContentReviewEvent,
    ContentVersion,
)
from aicmo.tenancy.context import TenantContext

# ---------------------------------------------------------------------
#  Review lifecycle
# ---------------------------------------------------------------------
REVIEW_STATUSES = (
    "draft", "in_review", "changes_requested", "approved", "rejected",
    "published", "archived",
)
_ALLOWED: dict[str, frozenset[str]] = {
    "draft": frozenset({"in_review", "archived"}),
    "in_review": frozenset({"changes_requested", "approved", "rejected"}),
    "changes_requested": frozenset({"in_review", "draft"}),
    "approved": frozenset({"published", "changes_requested", "archived"}),
    "rejected": frozenset({"draft", "archived"}),
    "published": frozenset({"archived"}),
    "archived": frozenset({"draft"}),
}


async def _owned_content(
    session: AsyncSession, *, tenant: TenantContext, content_id: uuid.UUID
) -> GeneratedContent:
    row = await session.get(GeneratedContent, content_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found.")
    return row


# ---------------------------------------------------------------------
#  Version history (immutable)
# ---------------------------------------------------------------------
async def snapshot_version(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    content: GeneratedContent,
    edit_source: str = "ai",
    change_summary: str | None = None,
) -> ContentVersion:
    """Append an immutable snapshot of the asset's current output. Does not
    commit (the caller's transaction persists it)."""
    next_no = (
        await session.execute(
            select(func.coalesce(func.max(ContentVersion.version_no), 0)).where(
                ContentVersion.content_id == content.id
            )
        )
    ).scalar_one() + 1
    row = ContentVersion(
        id=uuid.uuid4(),
        organization_id=content.organization_id,
        brand_id=content.brand_id,
        content_id=content.id,
        version_no=next_no,
        output=content.output,
        strategy=content.strategy,
        change_summary=change_summary,
        edit_source=edit_source,
        author_user_id=tenant.user_id,
    )
    session.add(row)
    return row


async def list_versions(
    session: AsyncSession, *, tenant: TenantContext, content_id: uuid.UUID
) -> list[ContentVersion]:
    await _owned_content(session, tenant=tenant, content_id=content_id)
    stmt = (
        select(ContentVersion)
        .where(ContentVersion.content_id == content_id)
        .order_by(desc(ContentVersion.version_no))
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_version(
    session: AsyncSession, *, tenant: TenantContext, content_id: uuid.UUID, version_no: int
) -> ContentVersion:
    await _owned_content(session, tenant=tenant, content_id=content_id)
    row = (
        await session.execute(
            select(ContentVersion).where(
                ContentVersion.content_id == content_id,
                ContentVersion.version_no == version_no,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found.")
    return row


async def restore_version(
    session: AsyncSession, *, tenant: TenantContext, content_id: uuid.UUID, version_no: int
) -> GeneratedContent:
    """Restore the asset to a prior version — captured as a NEW version so
    history stays immutable + linear."""
    content = await _owned_content(session, tenant=tenant, content_id=content_id)
    target = await get_version(session, tenant=tenant, content_id=content_id, version_no=version_no)
    content.output = target.output
    content.strategy = target.strategy
    await snapshot_version(
        session, tenant=tenant, content=content, edit_source="restore",
        change_summary=f"Restored from v{version_no}.",
    )
    await audit_service.record(
        session, organization_id=tenant.organization_id, actor_user_id=tenant.user_uuid,
        action="content.version_restored", brand_id=tenant.brand_id,
        target_type="generated_content", target_id=content.id,
        metadata={"restored_from": version_no},
    )
    await session.commit()
    await session.refresh(content)
    return content


# ---------------------------------------------------------------------
#  Manual edit (with a new version)
# ---------------------------------------------------------------------
async def apply_edit(
    session: AsyncSession, *, tenant: TenantContext, content_id: uuid.UUID,
    output: dict, change_summary: str | None,
) -> GeneratedContent:
    content = await _owned_content(session, tenant=tenant, content_id=content_id)
    content.output = output
    await snapshot_version(
        session, tenant=tenant, content=content, edit_source="manual",
        change_summary=change_summary,
    )
    await session.commit()
    await session.refresh(content)
    return content


# ---------------------------------------------------------------------
#  Approval workflow
# ---------------------------------------------------------------------
async def transition_review(
    session: AsyncSession, *, tenant: TenantContext, content_id: uuid.UUID,
    to_status: str, reason: str | None,
) -> GeneratedContent:
    content = await _owned_content(session, tenant=tenant, content_id=content_id)
    current = content.review_status or "draft"
    if to_status not in REVIEW_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown status {to_status!r}.")
    if to_status not in _ALLOWED.get(current, frozenset()):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot move from {current!r} to {to_status!r}.",
        )
    session.add(ContentReviewEvent(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        content_id=content.id, from_status=current, to_status=to_status,
        reason=reason, reviewer_user_id=tenant.user_id,
    ))
    content.review_status = to_status
    await audit_service.record(
        session, organization_id=tenant.organization_id, actor_user_id=tenant.user_uuid,
        action="content.review_transition", brand_id=tenant.brand_id,
        target_type="generated_content", target_id=content.id,
        metadata={"from": current, "to": to_status, "reason": reason},
    )
    await session.commit()
    await session.refresh(content)
    return content


async def review_history(
    session: AsyncSession, *, tenant: TenantContext, content_id: uuid.UUID
) -> list[ContentReviewEvent]:
    await _owned_content(session, tenant=tenant, content_id=content_id)
    stmt = (
        select(ContentReviewEvent)
        .where(ContentReviewEvent.content_id == content_id)
        .order_by(asc(ContentReviewEvent.created_at))
    )
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------
#  Folders / collections
# ---------------------------------------------------------------------
async def create_folder(
    session: AsyncSession, *, tenant: TenantContext, name: str, kind: str,
    parent_id: uuid.UUID | None,
) -> ContentFolder:
    if parent_id is not None:
        parent = await session.get(ContentFolder, parent_id)
        if parent is None or parent.brand_id != tenant.brand_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Parent folder not found.")
    row = ContentFolder(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        name=name, kind=kind, parent_id=parent_id, created_by_user_id=tenant.user_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_folders(
    session: AsyncSession, *, tenant: TenantContext
) -> list[ContentFolder]:
    stmt = (
        select(ContentFolder)
        .where(ContentFolder.brand_id == tenant.brand_id)
        .order_by(desc(ContentFolder.pinned), asc(ContentFolder.name))
    )
    return list((await session.execute(stmt)).scalars().all())


async def update_folder(
    session: AsyncSession, *, tenant: TenantContext, folder_id: uuid.UUID,
    name: str | None = None, pinned: bool | None = None,
) -> ContentFolder:
    row = await session.get(ContentFolder, folder_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found.")
    if name is not None:
        row.name = name
    if pinned is not None:
        row.pinned = pinned
    await session.commit()
    await session.refresh(row)
    return row


async def delete_folder(
    session: AsyncSession, *, tenant: TenantContext, folder_id: uuid.UUID
) -> None:
    row = await session.get(ContentFolder, folder_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found.")
    await session.delete(row)  # SET NULL on assigned content
    await session.commit()


async def assign_to_folder(
    session: AsyncSession, *, tenant: TenantContext, content_ids: list[uuid.UUID],
    folder_id: uuid.UUID | None,
) -> int:
    """Bulk-move assets into a folder (or unfile with folder_id=None)."""
    if folder_id is not None:
        folder = await session.get(ContentFolder, folder_id)
        if folder is None or folder.brand_id != tenant.brand_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Folder not found.")
    moved = 0
    for cid in content_ids:
        content = await session.get(GeneratedContent, cid)
        if content is None or content.brand_id != tenant.brand_id:
            continue  # skip anything not owned — never touch another tenant's rows
        content.folder_id = folder_id
        moved += 1
    await session.commit()
    return moved


# ---------------------------------------------------------------------
#  Comments + mentions
# ---------------------------------------------------------------------
async def add_comment(
    session: AsyncSession, *, tenant: TenantContext, content_id: uuid.UUID,
    body: str, parent_id: uuid.UUID | None, mentions: list[str],
) -> ContentComment:
    await _owned_content(session, tenant=tenant, content_id=content_id)
    if parent_id is not None:
        parent = await session.get(ContentComment, parent_id)
        if parent is None or parent.brand_id != tenant.brand_id or parent.content_id != content_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Parent comment not found.")
    row = ContentComment(
        id=uuid.uuid4(), organization_id=tenant.organization_id, brand_id=tenant.brand_id,
        content_id=content_id, parent_id=parent_id, author_user_id=tenant.user_id,
        body=body, mentions=list(mentions or []),
    )
    session.add(row)
    await audit_service.record(
        session, organization_id=tenant.organization_id, actor_user_id=tenant.user_uuid,
        action="content.commented", brand_id=tenant.brand_id,
        target_type="generated_content", target_id=content_id,
        metadata={"mentions": mentions or []},
    )
    await session.commit()
    await session.refresh(row)
    return row


async def list_comments(
    session: AsyncSession, *, tenant: TenantContext, content_id: uuid.UUID
) -> list[ContentComment]:
    await _owned_content(session, tenant=tenant, content_id=content_id)
    stmt = (
        select(ContentComment)
        .where(ContentComment.content_id == content_id)
        .order_by(asc(ContentComment.created_at))
    )
    return list((await session.execute(stmt)).scalars().all())


async def set_comment_resolved(
    session: AsyncSession, *, tenant: TenantContext, comment_id: uuid.UUID, resolved: bool
) -> ContentComment:
    row = await session.get(ContentComment, comment_id)
    if row is None or row.brand_id != tenant.brand_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found.")
    row.resolved = resolved
    row.resolved_by_user_id = tenant.user_id if resolved else None
    await session.commit()
    await session.refresh(row)
    return row


# ---------------------------------------------------------------------
#  Enterprise search (over the real asset + its links + status + folder)
# ---------------------------------------------------------------------
async def search_content(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    q: str | None = None,
    content_type: str | None = None,
    review_status: str | None = None,
    folder_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    strategy_id: uuid.UUID | None = None,
    saved_only: bool = False,
    limit: int = 30,
    offset: int = 0,
) -> tuple[list[GeneratedContent], int]:
    """Paginated, brand-scoped search across content + its links/status/folder.
    Returns (rows, total)."""
    base = select(GeneratedContent).where(
        GeneratedContent.brand_id == tenant.brand_id
    )
    if content_type:
        base = base.where(GeneratedContent.content_type == content_type)
    if review_status:
        base = base.where(GeneratedContent.review_status == review_status)
    if folder_id is not None:
        base = base.where(GeneratedContent.folder_id == folder_id)
    if campaign_id is not None:
        base = base.where(GeneratedContent.campaign_id == campaign_id)
    if strategy_id is not None:
        base = base.where(GeneratedContent.strategy_id == strategy_id)
    if saved_only:
        base = base.where(GeneratedContent.is_saved.is_(True))
    if q:
        like = f"%{q.lower()}%"
        base = base.where(
            func.lower(GeneratedContent.goal).like(like)
            | func.lower(GeneratedContent.platform).like(like)
            | func.lower(GeneratedContent.content_type).like(like)
            | cast(GeneratedContent.output, String).ilike(like)
        )
    total = (
        await session.execute(
            select(func.count()).select_from(base.subquery())
        )
    ).scalar_one()
    rows = list(
        (
            await session.execute(
                base.order_by(desc(GeneratedContent.created_at))
                .limit(max(1, min(limit, 100)))
                .offset(max(0, offset))
            )
        )
        .scalars()
        .all()
    )
    return rows, total
