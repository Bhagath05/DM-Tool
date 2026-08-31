"""S3Backend — production object storage (S3 / R2 / MinIO via `s3_endpoint_url`).

Bytes live here; Postgres holds only a `StorageRef`. boto3 is imported lazily so
dev + tests run without it installed, and in V0 the backend is never selected
(`media_backend` defaults to `local`).

Security posture (Phase 7B):
- **No static credentials in code.** boto3's default credential chain is used —
  on AWS (ECS/Fargate/Lambda/EC2) the task/instance **IAM role** supplies creds;
  no `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` are read or passed here.
- **Encryption at rest** — every object is written with SSE (AES256). Pair with
  the bucket's *default* encryption + Block-Public-Access (see
  docs/security/AWS_S3_HARDENING.md).
- **Bounded presigned URLs** — expiry is clamped to [60s, 1h] so a caller can
  never mint a long-lived public link; objects stay private otherwise.
- The client is injectable so this backend is unit-testable without AWS.
"""

from __future__ import annotations

from aicmo.config import get_settings
from aicmo.modules.creative.storage.base import StorageRef

# Server-side encryption for objects at rest (SSE-S3). Works alongside a
# bucket default-encryption policy; belt-and-suspenders.
_SSE = "AES256"
# Presigned URLs are a temporary capability, never a durable public link.
_MIN_EXPIRY_S = 60
_MAX_EXPIRY_S = 3600  # 1 hour hard cap


class S3NotConfigured(RuntimeError):
    pass


def _clamp_expiry(expires_s: int) -> int:
    return max(_MIN_EXPIRY_S, min(int(expires_s), _MAX_EXPIRY_S))


class S3Backend:
    name = "s3"

    def __init__(self, client=None):
        # Optional injected client — used by tests. Production leaves this None
        # and the real boto3 client is built lazily from the IAM-role chain.
        self._injected = client

    def _client(self):
        if self._injected is not None:
            return self._injected
        s = get_settings()
        if not s.s3_bucket:
            raise S3NotConfigured("S3_BUCKET is not set")
        try:
            import boto3
        except ImportError as e:  # pragma: no cover - env without boto3
            raise S3NotConfigured("the `boto3` package is not installed") from e
        # Default credential chain → IAM role on AWS. Region/endpoint only.
        return boto3.client(
            "s3",
            region_name=s.s3_region or None,
            endpoint_url=s.s3_endpoint_url or None,
        )

    def _bucket(self) -> str:
        return get_settings().s3_bucket

    def put(self, *, key: str, data: bytes, content_type: str) -> StorageRef:
        self._client().put_object(
            Bucket=self._bucket(),
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption=_SSE,
        )
        return StorageRef(backend=self.name, key=key)

    def signed_url(self, ref: StorageRef, *, expires_s: int = 3600) -> str:
        return self._client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket(), "Key": ref.key},
            ExpiresIn=_clamp_expiry(expires_s),
        )

    def head(self, ref: StorageRef) -> dict | None:
        """Object metadata (size/content-type/etc), or None if absent/denied."""
        try:
            return self._client().head_object(Bucket=self._bucket(), Key=ref.key)
        except Exception:
            return None

    def exists(self, ref: StorageRef) -> bool:
        return self.head(ref) is not None

    def delete(self, ref: StorageRef) -> None:
        self._client().delete_object(Bucket=self._bucket(), Key=ref.key)
