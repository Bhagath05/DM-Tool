"""Persist a generation job and run each selected model independently."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.ai_audit.service import (
    ACTION_GENERATE_CREATIVE,
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_SUCCESS,
    record_ai_generation,
)
from aicmo.modules.creative.cost import record_cost
from aicmo.modules.creative.gateway.executor import GenerationError, generate_image
from aicmo.modules.creative.gateway.models import CreativeGenerationJob
from aicmo.modules.creative.gateway.selection import SelectionError, plan_selection
from aicmo.modules.creative.storage.registry import get_storage_backend
from aicmo.tenancy.context import TenantContext


def _public_result(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_id": row["model_id"],
        "provider": row["provider"],
        "status": row["status"],
        "error": row.get("error"),
        "duration_ms": row.get("duration_ms"),
        "cost_cents": row.get("cost_cents"),
        "cost_unit": row.get("cost_unit"),
        "width": row.get("width"),
        "height": row.get("height"),
        "mime_type": row.get("mime_type"),
        "storage_backend": row.get("storage_backend"),
        "storage_key": row.get("storage_key"),
    }


async def run_generation(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    mode: str,
    task: str,
    prompt: str,
    model_ids: list[str] | None,
    aspect_ratio: str | None,
    resolution: str | None,
) -> CreativeGenerationJob:
    brand_id = tenant.brand_id
    if brand_id is None:
        raise SelectionError("A brand is required for generation.")
    plan = plan_selection(
        mode=mode,
        task=task,
        model_ids=model_ids,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
    )
    job = CreativeGenerationJob(
        id=uuid.uuid4(),
        organization_id=tenant.organization_id,
        brand_id=brand_id,
        user_id=tenant.user_id,
        mode=mode,
        task=task,
        status="running",
        prompt=prompt,
        params={
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "model_ids": [model.model_id for model in plan.models],
        },
        explanation=plan.explanation,
        results=[],
        attempt_count=0,
    )
    session.add(job)
    await session.flush()

    results: list[dict[str, Any]] = []
    storage = get_storage_backend()
    for model in plan.models:
        job.attempt_count += 1
        try:
            if task != "image.generate":
                raise GenerationError("This task has no verified executor in CS-1.")
            output = await generate_image(
                model,
                prompt=prompt,
                aspect_ratio=aspect_ratio or "1:1",
                resolution=resolution,
            )
            key = f"gateway/{brand_id}/{job.id}/{model.model_id}.png"
            ref = storage.put(key=key, data=output.image_bytes, content_type=output.mime)
            if output.cost_cents is not None:
                await record_cost(
                    session,
                    organization_id=tenant.organization_id,
                    brand_id=brand_id,
                    stage="gateway.image",
                    provider=output.provider,
                    cost_cents=output.cost_cents,
                    media_type="image",
                    units=1,
                    unit_cost_cents=float(output.cost_cents),
                    duration_ms=output.duration_ms,
                )
            results.append(
                {
                    "model_id": model.model_id,
                    "provider": output.provider,
                    "status": "succeeded",
                    "error": None,
                    "duration_ms": output.duration_ms,
                    "cost_cents": output.cost_cents,
                    "cost_unit": model.cost_unit,
                    "width": output.width,
                    "height": output.height,
                    "mime_type": output.mime,
                    "storage_backend": ref.backend,
                    "storage_key": ref.key,
                }
            )
        except GenerationError as exc:
            results.append(
                {
                    "model_id": model.model_id,
                    "provider": model.provider,
                    "status": "failed",
                    "error": str(exc)[:240],
                    "duration_ms": None,
                    "cost_cents": None,
                    "cost_unit": model.cost_unit,
                    "width": None,
                    "height": None,
                    "mime_type": None,
                    "storage_backend": None,
                    "storage_key": None,
                }
            )

    succeeded = [row for row in results if row["status"] == "succeeded"]
    job.results = [_public_result(row) for row in results]
    if succeeded and len(succeeded) == len(results):
        job.status = "succeeded"
        audit_status = STATUS_SUCCESS
    elif succeeded:
        job.status = "partial"
        audit_status = STATUS_PARTIAL
    else:
        job.status = "failed"
        job.error_message = results[0]["error"] if results else "Generation failed."
        audit_status = STATUS_FAILED

    await record_ai_generation(
        session,
        tenant=tenant,
        action_type=ACTION_GENERATE_CREATIVE,
        asset_id=job.id,
        model_used=",".join(model.model_id for model in plan.models),
        generation_status=audit_status,
        metadata={
            "gateway": True,
            "mode": mode,
            "task": task,
            "providers": [model.provider for model in plan.models],
        },
    )
    await session.commit()
    await session.refresh(job)
    return job


async def get_job(
    session: AsyncSession, *, tenant: TenantContext, job_id: uuid.UUID
) -> CreativeGenerationJob | None:
    return (
        await session.execute(
            select(CreativeGenerationJob).where(
                CreativeGenerationJob.id == job_id,
                CreativeGenerationJob.brand_id == tenant.brand_id,
                CreativeGenerationJob.organization_id == tenant.organization_id,
            )
        )
    ).scalar_one_or_none()


__all__ = ["SelectionError", "get_job", "run_generation"]
