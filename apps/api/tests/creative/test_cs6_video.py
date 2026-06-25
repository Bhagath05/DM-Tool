"""CS6 — Veo provider guard, design→video bridge, multi-scene render job,
publishing exports. The render-job + exports tests need live Postgres
(skipped if down), like the CV0 video test.
"""

from __future__ import annotations

import socket
import uuid

import pytest

_DSN = "postgresql://aicmo:aicmo@localhost:5432/aicmo"
_ADSN = "postgresql+psycopg://aicmo:aicmo@localhost:5432/aicmo"


def _pg_up() -> bool:
    try:
        s = socket.create_connection(("localhost", 5432), 0.3)
        s.close()
        return True
    except OSError:
        return False


# ---- Veo provider: creds-guarded, registry selection ----
def test_veo_requires_vertex_config(monkeypatch):
    from aicmo.config import get_settings
    from aicmo.modules.video.providers.veo import VeoConfigError, VeoProvider

    monkeypatch.setenv("VERTEX_PROJECT", "")
    get_settings.cache_clear()
    with pytest.raises(VeoConfigError):
        VeoProvider().submit("a dog running", aspect="9:16", width=1080, height=1920, duration_s=8)


def test_registry_selects_veo_or_stub(monkeypatch):
    from aicmo.config import get_settings
    from aicmo.modules.video.providers.registry import get_video_provider

    monkeypatch.setenv("VIDEO_DEFAULT_PROVIDER", "veo3")
    get_settings.cache_clear()
    assert get_video_provider().name == "veo3"
    monkeypatch.setenv("VIDEO_DEFAULT_PROVIDER", "stub")
    get_settings.cache_clear()
    assert get_video_provider().name == "stub"


# ---- design → scenes ----
def test_scenes_from_design():
    from aicmo.modules.video.bridge import scenes_from_design

    doc = {"version": 1, "aspect": "9:16", "pages": [
        {"background": {"kind": "color", "color": "#111"}, "duration_ms": 3000, "layers": [
            {"type": "text", "id": "h", "role": "headline", "text": "Hook line"},
            {"type": "text", "id": "s", "role": "subtitle", "text": "Value line"}]},
        {"background": {"kind": "color", "color": "#111"}, "duration_ms": 2000, "layers": [
            {"type": "text", "id": "c", "role": "cta", "text": "Get started"}]},
    ]}
    scenes = scenes_from_design(doc)
    assert len(scenes) == 2
    assert scenes[0]["duration_s"] == 3.0 and "Hook line" in scenes[0]["prompt"]
    assert scenes[0]["vo"] == "Value line"
    assert scenes[1]["cta"] == "Get started"


@pytest.fixture()
def tenant_rows():
    if not _pg_up():
        pytest.skip("Postgres not reachable")
    import psycopg

    conn = psycopg.connect(_DSN, connect_timeout=5)
    conn.autocommit = True
    cur = conn.cursor()
    uid, oid, bid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tag = uuid.uuid4().hex[:8]
    cur.execute("INSERT INTO users (id, clerk_user_id, email) VALUES (%s,%s,%s)",
                (uid, f"clerk_{tag}", f"{tag}@t.local"))
    cur.execute("INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (%s,%s,%s,%s)",
                (oid, f"org-{tag}", "T", uid))
    cur.execute("INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (%s,%s,%s,%s,%s)",
                (bid, oid, f"brand-{tag}", "B", uid))
    try:
        yield {"user_id": uid, "org_id": oid, "brand_id": bid}
    finally:
        cur.execute("DELETE FROM organizations WHERE id = %s", (oid,))
        cur.execute("DELETE FROM users WHERE id = %s", (uid,))
        conn.close()


@pytest.mark.asyncio
async def test_render_design_video_multi_scene(tenant_rows, monkeypatch):
    """Full multi-scene pipeline via the stub provider → ready, with per-scene
    renders, captions, and BOTH metering kinds (seconds summed)."""
    from aicmo.config import get_settings

    monkeypatch.setenv("DB_RLS_ENABLED", "false")
    monkeypatch.setenv("VIDEO_ENABLED", "true")
    monkeypatch.setenv("VIDEO_DEFAULT_PROVIDER", "stub")
    get_settings.cache_clear()
    import psycopg

    org, brand, user = tenant_rows["org_id"], tenant_rows["brand_id"], tenant_rows["user_id"]
    pid = uuid.uuid4()
    conn = psycopg.connect(_DSN, connect_timeout=5)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO creative_project (id,organization_id,brand_id,user_id,title,creative_type,"
        "media_type,format_slug,platform,status,spec,estimated_cost_cents) VALUES "
        "(%s,%s,%s,%s,'Reel','video','video','instagram_reels','instagram','draft',"
        "'{\"width\":1080,\"height\":1920,\"max_duration_s\":8,\"aspect_ratio\":\"9:16\",\"fps\":24,\"scenes\":2}'::jsonb,800)",
        (pid, org, brand, str(user)),
    )
    for i, (p, vo, dur) in enumerate([("Hook scene", "narration one", 3), ("CTA scene", "narration two", 2)]):
        cur.execute(
            "INSERT INTO video_scene (id,organization_id,brand_id,creative_project_id,scene_index,"
            "prompt,duration_s,vo_line,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pending')",
            (uuid.uuid4(), org, brand, pid, i, p, dur, vo),
        )

    from aicmo.modules.video.tasks import render_design_video
    from aicmo.queue.enqueue import TENANT_KW, TenantEnvelope

    payload = TenantEnvelope(
        user_uuid=str(user), organization_id=str(org), brand_id=str(brand), role_slugs=["owner"]
    ).to_payload()
    result = await render_design_video({}, str(pid), **{TENANT_KW: payload})

    assert result["status"] == "ready"
    assert result["scenes"] == 2
    assert result["seconds"] == 5  # 3 + 2

    cur.execute("SELECT status FROM creative_project WHERE id=%s", (pid,))
    assert cur.fetchone()[0] == "ready"
    cur.execute("SELECT count(*) FROM video_render WHERE creative_project_id=%s AND status='succeeded'", (pid,))
    assert cur.fetchone()[0] == 2  # one render per scene
    cur.execute("SELECT caption_storage_key FROM creative_asset WHERE creative_project_id=%s AND media_type='video'", (pid,))
    assert cur.fetchone()[0]  # captions (.vtt) stored
    cur.execute("SELECT quantity FROM usage_event WHERE organization_id=%s AND kind='video_second'", (org,))
    assert cur.fetchone()[0] == 5  # seconds metered = sum of scene durations
    cur.execute("SELECT count(*) FROM usage_event WHERE organization_id=%s AND kind='video_generation'", (org,))
    assert cur.fetchone()[0] == 1
    conn.close()


@pytest.mark.asyncio
async def test_prepare_exports_five_platforms(tenant_rows):
    """Exports re-target the SAME asset for 5 platforms (no re-encode in CS6)."""
    import psycopg
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from aicmo.modules.creative.design import video as vo
    from aicmo.tenancy.context import TenantContext

    org, brand, user = tenant_rows["org_id"], tenant_rows["brand_id"], tenant_rows["user_id"]
    pid, aid = uuid.uuid4(), uuid.uuid4()
    conn = psycopg.connect(_DSN, connect_timeout=5)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO creative_project (id,organization_id,brand_id,title,creative_type,media_type,status) "
        "VALUES (%s,%s,%s,'R','video','video','ready')", (pid, org, brand))
    cur.execute(
        "INSERT INTO creative_asset (id,organization_id,brand_id,creative_project_id,media_type,"
        "creative_type,storage_backend,storage_key,status) VALUES "
        "(%s,%s,%s,%s,'video','video','local','k/reel.mp4','ready')", (aid, org, brand, pid))

    eng = create_async_engine(_ADSN)
    async with AsyncSession(eng) as s:
        t = TenantContext(user_id="x", user_uuid=user, organization_id=org, brand_id=brand, member_id=user)
        exports = await vo.prepare_exports(
            s, tenant=t, asset_id=aid,
            platforms=["instagram_reels", "tiktok", "youtube_shorts", "facebook_reels", "linkedin"],
        )
        assert exports is not None and len(exports) == 5
        assert {e.target_platform for e in exports} == {
            "instagram_reels", "tiktok", "youtube_shorts", "facebook_reels", "linkedin"}
        await s.commit()
        listed = await vo.list_exports(s, tenant=t, asset_id=aid)
        assert len(listed) == 5
    await eng.dispose()
    conn.close()
