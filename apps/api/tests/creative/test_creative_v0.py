"""Creative Core V0 tests.

Pure unit tests always run. The end-to-end stub-pipeline test runs against
live Postgres (skipped if down): it creates a throwaway org/brand/user,
drives a creative_project draft → ready via the STUB providers + local
storage, and asserts the unified asset, cost ledger, and BOTH usage kinds
were written — proving the architecture with no network/spend. All rows
are cleaned up in teardown.
"""

from __future__ import annotations

import socket
import time
import uuid

import pytest

from aicmo.modules.creative.storage.base import StorageRef, sign_key, verify_key
from aicmo.modules.video.providers.stub import StubVideoProvider
from aicmo.modules.video.tts.stub import StubTTSProvider


def _pg_up() -> bool:
    s = socket.socket(); s.settimeout(2)
    try:
        s.connect(("localhost", 5432)); s.close(); return True
    except Exception:  # noqa: BLE001
        return False


_DSN = "postgresql://aicmo:aicmo@localhost:5432/aicmo"
_ADSN = "postgresql+psycopg://aicmo:aicmo@localhost:5432/aicmo"


# ---------------------------------------------------------------------
#  Pure unit
# ---------------------------------------------------------------------


def test_flag_defaults_off():
    # Ships-dark intent: assert the DECLARED code defaults, not an instantiated
    # Settings (which reads the dev .env, where the slideshow video path is on).
    from aicmo.config import Settings

    f = Settings.model_fields
    assert f["video_enabled"].default is False
    assert f["video_default_provider"].default == "stub"
    assert f["tts_default_provider"].default == "stub"
    assert f["media_backend"].default == "local"


def test_storage_ref_and_signing_round_trip():
    ref = StorageRef(backend="local", key="org/asset.mp4")
    assert ref.as_dict() == {"backend": "local", "key": "org/asset.mp4"}
    exp = int(time.time()) + 60
    sig = sign_key(ref.key, exp)
    ok, _ = verify_key(ref.key, exp, sig)
    assert ok
    bad, reason = verify_key(ref.key, exp, "deadbeef")
    assert not bad and reason == "bad_signature"
    expired, reason2 = verify_key(ref.key, int(time.time()) - 1, sign_key(ref.key, int(time.time()) - 1))
    assert not expired and reason2 == "expired"


def test_stub_providers_no_network():
    vp = StubVideoProvider()
    op = vp.submit("a cat", aspect="9:16", width=1080, height=1920, duration_s=8)
    st = vp.poll(op)
    assert st.state == "done" and st.result_bytes is not None
    assert vp.estimate_cost(duration_s=8, width=1080, height=1920) == 8 * 50

    tts = StubTTSProvider()
    audio = tts.synthesize("hello world", voice_id="v1")
    assert audio.startswith(b"STUBAUDIO")
    assert tts.estimate_cost(char_count=1000) == 30


def test_require_enabled_raises_when_flag_off(monkeypatch):
    from fastapi import HTTPException

    from aicmo.config import get_settings
    from aicmo.modules.creative.router import _require_enabled

    monkeypatch.setenv("VIDEO_ENABLED", "false")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        _require_enabled()
    assert exc.value.status_code == 409
    get_settings.cache_clear()


def test_boot_guard_requires_secrets_when_video_live(monkeypatch):
    from aicmo.config import Settings, validate_production_secrets

    base = dict(
        api_env="production", auth_mode="clerk",
        clerk_secret_key="sk_live_x", clerk_jwt_issuer="https://r.clerk.dev",
        clerk_jwks_url="https://r.clerk.dev/jwks", clerk_jwt_audience="aud",
        ip_hash_pepper="x" * 32, media_signing_secret="y" * 32,
        sentry_dsn="https://k@o.ingest.sentry.io/1",
        anthropic_api_key="sk-ant-real", llm_default_provider="anthropic",
        video_enabled=True, video_default_provider="veo3",  # but no vertex creds
    )
    with pytest.raises(SystemExit) as exc:
        validate_production_secrets(Settings(**base))
    assert "VERTEX_PROJECT" in str(exc.value)
    # video-on but stub providers → boots fine.
    ok = Settings(**{**base, "video_default_provider": "stub"})
    validate_production_secrets(ok)  # no raise


# ---------------------------------------------------------------------
#  Live stub-pipeline (skip if PG down)
# ---------------------------------------------------------------------


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
    cur.execute(
        "INSERT INTO users (id, clerk_user_id, email) VALUES (%s,%s,%s)",
        (uid, f"clerk_{tag}", f"{tag}@test.local"),
    )
    cur.execute(
        "INSERT INTO organizations (id, slug, name, owner_user_id) VALUES (%s,%s,%s,%s)",
        (oid, f"org-{tag}", "Test Org", uid),
    )
    cur.execute(
        "INSERT INTO brands (id, organization_id, slug, name, created_by_user_id) VALUES (%s,%s,%s,%s,%s)",
        (bid, oid, f"brand-{tag}", "Test Brand", uid),
    )
    try:
        yield {"user_id": uid, "org_id": oid, "brand_id": bid}
    finally:
        cur.execute("DELETE FROM organizations WHERE id = %s", (oid,))  # cascades creative rows
        cur.execute("DELETE FROM users WHERE id = %s", (uid,))
        conn.close()


@pytest.mark.asyncio
async def test_stub_pipeline_draft_to_ready(tenant_rows, monkeypatch):
    """End-to-end: project draft → ready with asset + cost + both usage
    kinds, no network."""
    from aicmo.config import get_settings

    monkeypatch.setenv("DB_RLS_ENABLED", "false")
    monkeypatch.setenv("VIDEO_ENABLED", "true")
    get_settings.cache_clear()

    import psycopg

    org, brand, user = tenant_rows["org_id"], tenant_rows["brand_id"], tenant_rows["user_id"]
    pid = uuid.uuid4()

    conn = psycopg.connect(_DSN, connect_timeout=5)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO creative_project "
        "(id, organization_id, brand_id, user_id, title, creative_type, media_type, "
        " format_slug, platform, status, spec, estimated_cost_cents) "
        "VALUES (%s,%s,%s,%s,'Test reel','video','video','instagram_reels','instagram','draft',"
        " '{\"width\":1080,\"height\":1920,\"max_duration_s\":8,\"aspect_ratio\":\"9:16\",\"fps\":24}'::jsonb, 400)",
        (pid, org, brand, str(user)),
    )

    # Run the stub pipeline job (opens its own session).
    from aicmo.modules.video.tasks import generate_video_stub
    from aicmo.queue.enqueue import TENANT_KW, TenantEnvelope

    payload = TenantEnvelope(
        user_uuid=str(user), organization_id=str(org), brand_id=str(brand), role_slugs=["owner"]
    ).to_payload()
    result = await generate_video_stub({}, str(pid), **{TENANT_KW: payload})
    assert result["status"] == "ready"

    # Assert downstream writes.
    cur.execute("SELECT status, actual_cost_cents FROM creative_project WHERE id=%s", (pid,))
    status_, actual = cur.fetchone()
    assert status_ == "ready"
    assert actual > 0  # cost rolled up from the ledger

    cur.execute("SELECT count(*) FROM creative_asset WHERE creative_project_id=%s AND media_type='video'", (pid,))
    assert cur.fetchone()[0] == 1  # unified asset registered

    cur.execute("SELECT count(*) FROM video_render WHERE creative_project_id=%s AND status='succeeded'", (pid,))
    assert cur.fetchone()[0] == 1

    cur.execute("SELECT count(*) FROM creative_cost_event WHERE creative_project_id=%s", (pid,))
    assert cur.fetchone()[0] >= 2  # veo_clip + tts

    cur.execute("SELECT count(*) FROM usage_event WHERE organization_id=%s AND kind='video_generation'", (org,))
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT coalesce(sum(quantity),0) FROM usage_event WHERE organization_id=%s AND kind='video_second'", (org,))
    assert cur.fetchone()[0] > 0

    conn.close()
    get_settings.cache_clear()


def test_creative_format_seeded():
    if not _pg_up():
        pytest.skip("Postgres not reachable")
    import psycopg

    conn = psycopg.connect(_DSN, connect_timeout=5)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM creative_format WHERE is_active AND media_type='video'")
    assert cur.fetchone()[0] == 7
    conn.close()
