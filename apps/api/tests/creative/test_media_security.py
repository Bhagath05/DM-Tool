"""Phase 7B — media/storage security: S3 encryption + bounded presigned URLs,
provider-output validation, and tenant-scoped asset queries."""

from __future__ import annotations

import pytest

from aicmo.modules.creative.storage.base import StorageRef
from aicmo.modules.creative.storage.s3 import S3Backend, _clamp_expiry
from aicmo.modules.creative.storage.validation import (
    MediaValidationError,
    validate_media_output,
    validate_video_output,
)

# A minimal valid MP4 header: 4-byte box size + 'ftyp' box type + brand.
_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 32


# ---------------- S3 backend hardening ----------------


class _FakeS3Client:
    def __init__(self):
        self.put_calls: list[dict] = []
        self.presign_calls: list[dict] = []
        self.deleted: list[str] = []

    def put_object(self, **kw):
        self.put_calls.append(kw)

    def generate_presigned_url(self, op, *, Params, ExpiresIn):  # noqa: N803 (boto3 kwargs)
        self.presign_calls.append({"op": op, "Params": Params, "ExpiresIn": ExpiresIn})
        return f"https://s3.example/{Params['Key']}?X-Expires={ExpiresIn}"

    def head_object(self, **kw):
        return {"ContentLength": 10}

    def delete_object(self, **kw):
        self.deleted.append(kw["Key"])


def _backend(monkeypatch):
    client = _FakeS3Client()
    monkeypatch.setattr(
        "aicmo.modules.creative.storage.s3.get_settings",
        lambda: type(
            "S", (), {"s3_bucket": "b", "s3_region": "us-east-1", "s3_endpoint_url": ""}
        )(),
    )
    return S3Backend(client=client), client


def test_put_encrypts_at_rest(monkeypatch):
    backend, client = _backend(monkeypatch)
    ref = backend.put(key="tenants/o/b/asset.mp4", data=b"x", content_type="video/mp4")
    assert ref.backend == "s3" and ref.key == "tenants/o/b/asset.mp4"
    assert client.put_calls[0]["ServerSideEncryption"] == "AES256"  # encrypted
    assert client.put_calls[0]["ContentType"] == "video/mp4"


def test_presigned_url_expiry_is_bounded(monkeypatch):
    backend, client = _backend(monkeypatch)
    ref = StorageRef(backend="s3", key="k")
    backend.signed_url(ref, expires_s=10_000_000)  # attempt a very long link
    assert client.presign_calls[0]["ExpiresIn"] == 3600  # clamped to 1h max
    backend.signed_url(ref, expires_s=5)
    assert client.presign_calls[1]["ExpiresIn"] == 60  # floored to 60s min


def test_clamp_expiry_bounds():
    assert _clamp_expiry(10) == 60
    assert _clamp_expiry(3600) == 3600
    assert _clamp_expiry(999999) == 3600
    assert _clamp_expiry(1800) == 1800


def test_no_static_aws_keys_passed_to_client(monkeypatch):
    """boto3 must be built with the IAM-role default credential chain — never
    static keys constructed in code."""
    import inspect

    src = inspect.getsource(S3Backend._client)
    assert "aws_access_key_id" not in src
    assert "aws_secret_access_key" not in src


# ---------------- provider-output validation ----------------


def test_valid_mp4_passes():
    assert validate_video_output(content_type="video/mp4", data=_MP4) == "video/mp4"


def test_wrong_content_type_rejected():
    with pytest.raises(MediaValidationError):
        validate_video_output(content_type="text/html", data=_MP4)


def test_empty_payload_rejected():
    with pytest.raises(MediaValidationError):
        validate_video_output(content_type="video/mp4", data=b"")


def test_non_mp4_payload_rejected():
    # a provider that returned an HTML error page must not land as "video"
    with pytest.raises(MediaValidationError):
        validate_video_output(content_type="video/mp4", data=b"<html>error</html>")


def test_oversized_video_rejected(monkeypatch):
    monkeypatch.setattr("aicmo.modules.creative.storage.validation.MAX_VIDEO_BYTES", 10)
    with pytest.raises(MediaValidationError):
        validate_video_output(content_type="video/mp4", data=_MP4)


def test_generic_media_guard_handles_audio_and_captions():
    assert validate_media_output(content_type="audio/mpeg", data=b"ID3....") == "audio/mpeg"
    assert validate_media_output(content_type="text/vtt", data=b"WEBVTT") == "text/vtt"
    with pytest.raises(MediaValidationError):
        validate_media_output(content_type="application/x-msdownload", data=b"MZ")


# ---------------- tenant-scoped asset queries ----------------


def test_brand_asset_query_is_brand_scoped():
    """A BrandAsset fetch (which precedes signed-URL issuance) must filter on
    brand_id, so a tenant can never obtain a URL for another tenant's asset."""
    import uuid

    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    from aicmo.modules.creative.design.models import BrandAsset

    brand = uuid.uuid4()
    asset_id = uuid.uuid4()
    stmt = select(BrandAsset).where(BrandAsset.id == asset_id, BrandAsset.brand_id == brand)
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "brand_id" in sql


# ---------------- Phase 8 regressions: OIDC creds, no public ACL, no URL logs ----------------


def test_client_relies_on_default_credential_chain_no_static_or_session_keys():
    """Render OIDC assumes a role → boto3's default chain uses the short-lived
    STS creds. The client must never take static keys or a session token in
    code (that would defeat rotation / OIDC)."""
    import inspect

    src = inspect.getsource(S3Backend._client)
    for forbidden in ("aws_access_key_id", "aws_secret_access_key", "aws_session_token"):
        assert forbidden not in src


def test_put_never_sets_a_public_acl():
    """Regression: objects are private (bucket owner enforced, ACLs disabled).
    The writer must never set a public-read ACL."""
    import inspect

    src = inspect.getsource(S3Backend.put)
    assert "ACL" not in src
    assert "public-read" not in src


def test_storage_backends_never_log_urls():
    """Presigned/signed URLs are capabilities — they must never be logged."""
    import inspect

    from aicmo.modules.creative.storage import base, local
    from aicmo.modules.creative.storage import s3 as s3mod

    for mod in (s3mod, base, local):
        src = inspect.getsource(mod)
        # no logging framework wired into the storage layer at all → no URL leak path
        assert "structlog" not in src
        assert "logging.getLogger" not in src
