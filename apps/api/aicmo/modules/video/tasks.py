"""Video subsystem pipeline — Creative Core V0 (stub).

A single tenant-scoped Arq job that drives a creative_project
draft → ready using the STUB providers + local storage — no network, no
spend. It exercises the full architecture so V1 can swap stubs for real
Veo/ElevenLabs/S3 without changing the shape:

  submit → poll (the async provider seam) → store bytes (StorageBackend) →
  video_render row → creative_asset registration → cost ledger →
  usage metering → AI audit → status=ready.

V1 splits this into the multi-job poll fan-out (render_scene + poll_render
with defer_by backoff) — required because real Veo is genuinely
long-running. The stub returns instantly, so V0 keeps it in one job while
proving every downstream write.

Runs only when enqueued by the flag-gated /start endpoint; registered in
ALL_JOBS via queue/worker.py.
"""

from __future__ import annotations

import uuid

import structlog

from aicmo.modules.ai_audit.service import ACTION_GENERATE_REEL, record_ai_generation
from aicmo.modules.creative import cost as cost_ledger
from aicmo.modules.creative import metering
from aicmo.config import get_settings
from aicmo.modules.creative import service as creative_service
from aicmo.modules.creative.models import CreativeAsset
from aicmo.modules.creative.storage.base import StorageRef
from aicmo.modules.creative.storage.registry import get_storage_backend
from aicmo.modules.video.models import VideoRender, VideoScene
from aicmo.modules.video.providers.registry import get_video_provider
from aicmo.modules.video.tts.registry import get_tts_provider
from aicmo.queue.context import tenant_job
from aicmo.queue.enqueue import TenantEnvelope

log = structlog.get_logger()


@tenant_job
async def generate_video_stub(ctx, session, tenant: TenantEnvelope, project_id: str):
    """Drive one project to `ready` via the stub providers."""
    org = tenant.org_uuid()
    brand = tenant.brand_uuid()
    pid = uuid.UUID(project_id)

    # Load under the job's RLS-scoped session.
    project = await session.get(creative_service.CreativeProject, pid)
    if project is None or project.organization_id != org:
        log.warning("video.stub.project_missing", project_id=project_id)
        return {"status": "missing"}

    spec = project.spec or {}
    width = int(spec.get("width") or 1080)
    height = int(spec.get("height") or 1920)
    duration_s = int(spec.get("max_duration_s") or 8)

    provider = get_video_provider()
    tts = get_tts_provider()
    storage = get_storage_backend()

    project.status = "rendering"
    await session.flush()

    # --- one scene (V0) ---
    scene = VideoScene(
        organization_id=org, brand_id=brand, creative_project_id=pid,
        scene_index=0, prompt=(project.brief or project.title)[:2000],
        duration_s=min(duration_s, 8), status="rendering",
    )
    session.add(scene)
    await session.flush()

    # --- provider submit → poll (the async seam) ---
    op = provider.submit(
        scene.prompt, aspect=spec.get("aspect_ratio") or "9:16",
        width=width, height=height, duration_s=float(scene.duration_s),
    )
    status = provider.poll(op)
    clip_cost = provider.estimate_cost(duration_s=float(scene.duration_s), width=width, height=height)

    if status.state != "done" or status.result_bytes is None:
        scene.status = "failed"
        project.status = "failed_rendering"
        await session.flush()
        return {"status": project.status}

    # --- store the clip bytes (no bytes in PG) ---
    clip_ref = storage.put(
        key=f"{org}/{pid}/scene0.mp4", data=status.result_bytes, content_type="video/mp4"
    )
    render = VideoRender(
        organization_id=org, brand_id=brand, user_id=project.user_id,
        video_scene_id=scene.id, creative_project_id=pid,
        provider=provider.name, provider_operation_id=op.op_id,
        prompt=scene.prompt, storage_backend=clip_ref.backend, storage_key=clip_ref.key,
        width=width, height=height, fps=int(spec.get("fps") or 24),
        duration_ms=int(scene.duration_s) * 1000,
        has_native_audio=status.has_native_audio,
        synthid_watermark=status.synthid_watermark,
        status="succeeded", cost_cents=clip_cost,
    )
    session.add(render)
    scene.status = "done"
    await session.flush()
    await cost_ledger.record_cost(
        session, organization_id=org, brand_id=brand, creative_project_id=pid,
        media_type="video", stage="veo_clip", provider=provider.name,
        cost_cents=clip_cost, units=float(scene.duration_s),
        duration_ms=render.duration_ms,
    )

    # --- TTS voiceover (always layered — Decision 1) ---
    project.status = "post_processing"
    await session.flush()
    vo_text = (project.goal or project.title)[:500]
    audio = tts.synthesize(vo_text, voice_id="stub-voice")
    audio_ref = storage.put(key=f"{org}/{pid}/voiceover.mp3", data=audio, content_type="audio/mpeg")
    tts_cost = tts.estimate_cost(char_count=len(vo_text))
    await cost_ledger.record_cost(
        session, organization_id=org, brand_id=brand, creative_project_id=pid,
        media_type="video", stage="tts", provider=tts.name, cost_cents=tts_cost,
        units=len(vo_text),
    )

    # --- register the unified creative_asset (the Asset Library row) ---
    asset = CreativeAsset(
        organization_id=org, brand_id=brand, user_id=project.user_id,
        creative_project_id=pid, variant_label="A",
        media_type="video", creative_type="video",
        source_kind="video_render", source_id=render.id,
        storage_backend=clip_ref.backend, storage_key=clip_ref.key,
        caption_storage_key=audio_ref.key,
        mime_type="video/mp4", aspect_ratio=spec.get("aspect_ratio"),
        width=width, height=height, duration_ms=render.duration_ms,
        status="ready",
    )
    session.add(asset)
    await session.flush()

    # --- metering (both kinds — Decision 3) ---
    await metering.record_video_usage(
        session, organization_id=org, user_uuid=tenant.user_id_uuid(),
        brand_id=brand, seconds=int(scene.duration_s),
    )

    # --- AI audit (no content stored) ---
    project.actual_cost_cents = await cost_ledger.project_cost_cents(session, creative_project_id=pid)
    project.status = "ready"
    await session.flush()

    # ai_audit needs a TenantContext-shaped object; build a minimal one.
    from aicmo.tenancy.context import TenantContext

    tctx = TenantContext(
        user_id=str(tenant.user_id_uuid()), user_uuid=tenant.user_id_uuid(),
        organization_id=org, brand_id=brand, member_id=tenant.user_id_uuid(),
    )
    await record_ai_generation(
        session, tenant=tctx, action_type=ACTION_GENERATE_REEL,
        asset_id=asset.id, model_used=f"{provider.name}+{tts.name}",
        metadata={"media_type": "video", "format": project.format_slug,
                  "scenes": 1, "cost_cents": project.actual_cost_cents},
    )

    return {"status": "ready", "asset_id": str(asset.id), "cost_cents": project.actual_cost_cents}


def _vtt(scenes: list) -> str:
    """Build WebVTT captions from scene voiceover lines (cumulative timing)."""
    lines = ["WEBVTT", ""]
    t = 0.0
    for sc in scenes:
        dur = float(sc.duration_s or 2)
        start, end = t, t + dur
        if sc.vo_line:
            lines.append(f"{_ts(start)} --> {_ts(end)}")
            lines.append(sc.vo_line)
            lines.append("")
        t = end
    return "\n".join(lines)


def _ts(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}"


@tenant_job
async def render_design_video(ctx, session, tenant: TenantEnvelope, project_id: str):
    """Render a multi-scene reel (CS6). Per-scene submit→poll→store; combined
    TTS voiceover + WebVTT captions stored separately; assembled MP4 registered
    as a creative_asset. Reuses the same async provider seam as the V0 stub, so
    flipping VIDEO_DEFAULT_PROVIDER=veo3 renders for real with no shape change."""
    from sqlalchemy import select

    org = tenant.org_uuid()
    brand = tenant.brand_uuid()
    pid = uuid.UUID(project_id)

    project = await session.get(creative_service.CreativeProject, pid)
    if project is None or project.organization_id != org:
        log.warning("video.render.project_missing", project_id=project_id)
        return {"status": "missing"}

    spec = project.spec or {}
    width = int(spec.get("width") or 1080)
    height = int(spec.get("height") or 1920)
    aspect = spec.get("aspect_ratio") or "9:16"
    fps = int(spec.get("fps") or 24)

    scenes = list(
        (
            await session.execute(
                select(VideoScene)
                .where(VideoScene.creative_project_id == pid)
                .order_by(VideoScene.scene_index)
            )
        ).scalars().all()
    )
    if not scenes:
        project.status = "failed_rendering"
        await session.flush()
        return {"status": "no_scenes"}

    # --- slideshow mode: render the design's pages to a REAL MP4 locally
    # (Pillow frames + bundled ffmpeg), no external video API. ---
    if get_settings().video_default_provider == "slideshow":
        return await _render_slideshow(
            session, tenant=tenant, project=project, scenes=scenes,
            width=width, height=height, aspect=aspect, fps=fps,
        )

    provider = get_video_provider()
    tts = get_tts_provider()
    storage = get_storage_backend()

    project.status = "rendering"
    await session.flush()

    clip_parts: list[bytes] = []
    total_seconds = 0
    last_render = None
    try:
        for sc in scenes:
            sc.status = "rendering"
            await session.flush()
            dur = float(sc.duration_s or 8)
            op = provider.submit(sc.prompt, aspect=aspect, width=width, height=height, duration_s=dur)
            st = provider.poll(op)
            cost = provider.estimate_cost(duration_s=dur, width=width, height=height)
            if st.state != "done" or st.result_bytes is None:
                sc.status = "failed"
                project.status = "failed_rendering"
                await session.flush()
                return {"status": project.status, "scene": sc.scene_index, "error": st.error}
            ref = storage.put(
                key=f"{org}/{pid}/scene{sc.scene_index}.mp4",
                data=st.result_bytes, content_type="video/mp4",
            )
            last_render = VideoRender(
                organization_id=org, brand_id=brand, user_id=project.user_id,
                video_scene_id=sc.id, creative_project_id=pid, provider=provider.name,
                provider_operation_id=op.op_id, prompt=sc.prompt,
                storage_backend=ref.backend, storage_key=ref.key,
                width=width, height=height, fps=fps, duration_ms=int(dur * 1000),
                has_native_audio=st.has_native_audio, synthid_watermark=st.synthid_watermark,
                status="succeeded", cost_cents=cost,
            )
            session.add(last_render)
            sc.status = "done"
            await session.flush()
            await cost_ledger.record_cost(
                session, organization_id=org, brand_id=brand, creative_project_id=pid,
                media_type="video", stage="veo_clip", provider=provider.name,
                cost_cents=cost, units=dur, duration_ms=int(dur * 1000),
            )
            clip_parts.append(st.result_bytes)
            total_seconds += int(round(dur))
    except Exception as e:  # noqa: BLE001 — provider/network failure → fail the render cleanly
        log.warning("video.render.failed", project_id=project_id, error=str(e))
        project.status = "failed_rendering"
        await session.flush()
        return {"status": "failed_rendering", "error": str(e)}

    # --- assemble (stub: concat clip bytes; V1+ does ffmpeg concat + audio mux) ---
    project.status = "post_processing"
    await session.flush()
    reel_ref = storage.put(key=f"{org}/{pid}/reel.mp4", data=b"".join(clip_parts), content_type="video/mp4")

    # --- voiceover (combined) + captions (.vtt), stored separately ---
    vo_text = " ".join(sc.vo_line for sc in scenes if sc.vo_line)[:2000] or project.title
    audio = tts.synthesize(vo_text, voice_id="stub-voice")
    audio_ref = storage.put(key=f"{org}/{pid}/voiceover.mp3", data=audio, content_type="audio/mpeg")
    caption_ref = storage.put(
        key=f"{org}/{pid}/captions.vtt", data=_vtt(scenes).encode(), content_type="text/vtt"
    )
    await cost_ledger.record_cost(
        session, organization_id=org, brand_id=brand, creative_project_id=pid,
        media_type="video", stage="tts", provider=tts.name,
        cost_cents=tts.estimate_cost(char_count=len(vo_text)), units=len(vo_text),
    )

    # --- register the unified creative_asset (the reel) ---
    asset = CreativeAsset(
        organization_id=org, brand_id=brand, user_id=project.user_id,
        creative_project_id=pid, variant_label="A", media_type="video", creative_type="video",
        source_kind="video_render", source_id=last_render.id if last_render else None,
        storage_backend=reel_ref.backend, storage_key=reel_ref.key,
        caption_storage_key=caption_ref.key, poster_storage_key=audio_ref.key,
        mime_type="video/mp4", aspect_ratio=aspect, width=width, height=height,
        duration_ms=total_seconds * 1000, status="ready",
    )
    session.add(asset)
    await session.flush()

    # --- metering (video_generation + video_seconds across all scenes) ---
    await metering.record_video_usage(
        session, organization_id=org, user_uuid=tenant.user_id_uuid(),
        brand_id=brand, seconds=total_seconds,
    )

    project.actual_cost_cents = await cost_ledger.project_cost_cents(session, creative_project_id=pid)
    project.status = "ready"
    await session.flush()

    from aicmo.tenancy.context import TenantContext

    tctx = TenantContext(
        user_id=str(tenant.user_id_uuid()), user_uuid=tenant.user_id_uuid(),
        organization_id=org, brand_id=brand, member_id=tenant.user_id_uuid(),
    )
    await record_ai_generation(
        session, tenant=tctx, action_type=ACTION_GENERATE_REEL, asset_id=asset.id,
        model_used=f"{provider.name}+{tts.name}",
        metadata={"media_type": "video", "format": project.format_slug,
                  "scenes": len(scenes), "seconds": total_seconds,
                  "cost_cents": project.actual_cost_cents},
    )
    return {"status": "ready", "asset_id": str(asset.id), "scenes": len(scenes),
            "seconds": total_seconds, "cost_cents": project.actual_cost_cents}


async def _render_slideshow(
    session, *, tenant: TenantEnvelope, project, scenes, width: int, height: int, aspect: str, fps: int
):
    """Render the reel design's pages to a real MP4 with Pillow + bundled ffmpeg.

    The editable `creative_design` is the source of truth: each page → one frame
    (hero image cover + scrim + wrapped copy), assembled with the per-scene
    durations + combined TTS voiceover into a genuine, playable file. No GCP.
    """
    from aicmo.modules.creative.design.models import BrandAsset, CreativeDesign
    from aicmo.modules.video import slideshow

    org = tenant.org_uuid()
    brand = tenant.brand_uuid()
    pid = project.id
    spec = project.spec or {}
    storage = get_storage_backend()
    tts = get_tts_provider()

    # Load the design doc (source of truth) for the rich page layers.
    pages: list[dict] = []
    design_id = spec.get("design_id")
    if design_id:
        design = await session.get(CreativeDesign, uuid.UUID(design_id))
        if design is not None and design.organization_id == org:
            pages = (design.doc or {}).get("pages", [])
    if not pages:
        # Doc unavailable → text-only frames from the scene prompts.
        pages = [
            {"layers": [{"type": "text", "role": "headline", "text": sc.prompt,
                         "x": 0.08, "y": 0.4, "w": 0.84, "font_size": 0.06,
                         "align": "center", "color": "#ffffff"}]}
            for sc in scenes
        ]

    scene_by_idx = {sc.scene_index: sc for sc in scenes}

    project.status = "rendering"
    await session.flush()

    frames: list[tuple[bytes, float]] = []
    total_seconds = 0
    try:
        for i, page in enumerate(pages):
            sc = scene_by_idx.get(i)
            dur = float(sc.duration_s) if sc and sc.duration_s else 2.5
            image_bytes: bytes | None = None
            asset_id = slideshow.first_image_asset_id(page)
            if asset_id:
                asset = await session.get(BrandAsset, uuid.UUID(asset_id))
                if asset is not None and asset.brand_id == brand and asset.storage_key:
                    try:
                        image_bytes = storage.read(
                            StorageRef(backend=asset.storage_backend, key=asset.storage_key)
                        )
                    except Exception as e:  # noqa: BLE001
                        log.warning("slideshow.asset_read_failed", asset_id=asset_id, error=str(e))
            frames.append(
                (slideshow.render_page_png(page, width=width, height=height, image_bytes=image_bytes), dur)
            )
            if sc is not None:
                sc.status = "done"
            total_seconds += int(round(dur))
        await session.flush()

        # Combined TTS voiceover (always layered — Decision 1).
        project.status = "post_processing"
        await session.flush()
        vo_text = " ".join(sc.vo_line for sc in scenes if sc.vo_line)[:2000] or project.title
        audio = tts.synthesize(vo_text, voice_id="stub-voice")

        mp4 = slideshow.assemble_mp4(frames, audio_bytes=audio, width=width, height=height, fps=fps)
    except Exception as e:  # noqa: BLE001 — Pillow/ffmpeg failure → fail cleanly
        log.warning("slideshow.render_failed", project_id=str(pid), error=str(e))
        project.status = "failed_rendering"
        await session.flush()
        return {"status": "failed_rendering", "error": str(e)}

    reel_ref = storage.put(key=f"{org}/{pid}/reel.mp4", data=mp4, content_type="video/mp4")
    audio_ref = storage.put(key=f"{org}/{pid}/voiceover.mp3", data=audio, content_type="audio/mpeg")
    caption_ref = storage.put(
        key=f"{org}/{pid}/captions.vtt", data=_vtt(scenes).encode(), content_type="text/vtt"
    )

    tts_cost = tts.estimate_cost(char_count=len(vo_text))
    await cost_ledger.record_cost(
        session, organization_id=org, brand_id=brand, creative_project_id=pid,
        media_type="video", stage="tts", provider=tts.name, cost_cents=tts_cost, units=len(vo_text),
    )

    render = VideoRender(
        organization_id=org, brand_id=brand, user_id=project.user_id,
        video_scene_id=scenes[0].id, creative_project_id=pid, provider="slideshow",
        provider_operation_id="slideshow-local", prompt=(project.title or "reel")[:2000],
        storage_backend=reel_ref.backend, storage_key=reel_ref.key,
        width=width, height=height, fps=fps, duration_ms=total_seconds * 1000,
        has_native_audio=True, synthid_watermark=False, status="succeeded", cost_cents=0,
    )
    session.add(render)
    await session.flush()

    asset = CreativeAsset(
        organization_id=org, brand_id=brand, user_id=project.user_id,
        creative_project_id=pid, variant_label="A", media_type="video", creative_type="video",
        source_kind="video_render", source_id=render.id,
        storage_backend=reel_ref.backend, storage_key=reel_ref.key,
        caption_storage_key=caption_ref.key, poster_storage_key=audio_ref.key,
        mime_type="video/mp4", aspect_ratio=aspect, width=width, height=height,
        duration_ms=total_seconds * 1000, status="ready",
    )
    session.add(asset)
    await session.flush()

    await metering.record_video_usage(
        session, organization_id=org, user_uuid=tenant.user_id_uuid(), brand_id=brand, seconds=total_seconds,
    )
    project.actual_cost_cents = await cost_ledger.project_cost_cents(session, creative_project_id=pid)
    project.status = "ready"
    await session.flush()

    from aicmo.tenancy.context import TenantContext

    tctx = TenantContext(
        user_id=str(tenant.user_id_uuid()), user_uuid=tenant.user_id_uuid(),
        organization_id=org, brand_id=brand, member_id=tenant.user_id_uuid(),
    )
    await record_ai_generation(
        session, tenant=tctx, action_type=ACTION_GENERATE_REEL, asset_id=asset.id,
        model_used=f"slideshow+{tts.name}",
        metadata={"media_type": "video", "format": project.format_slug,
                  "scenes": len(frames), "seconds": total_seconds,
                  "cost_cents": project.actual_cost_cents},
    )
    return {"status": "ready", "asset_id": str(asset.id), "scenes": len(frames),
            "seconds": total_seconds, "cost_cents": project.actual_cost_cents, "provider": "slideshow"}
