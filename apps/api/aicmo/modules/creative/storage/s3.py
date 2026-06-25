"""S3Backend — prod object storage (interface; impl lands in V1).

S3-compatible (AWS / Cloudflare R2 / MinIO via `s3_endpoint_url`). boto3 is
imported lazily so V0 + tests run without it installed. In V0 the backend
is never selected (`media_backend` defaults to `local`); calling it raises
a clear error rather than a silent failure.
"""

from __future__ import annotations

from aicmo.config import get_settings
from aicmo.modules.creative.storage.base import StorageRef


class S3NotConfigured(RuntimeError):
    pass


class S3Backend:
    name = "s3"

    def _client(self):  # pragma: no cover - exercised in V1
        s = get_settings()
        if not s.s3_bucket:
            raise S3NotConfigured("S3_BUCKET is not set")
        try:
            import boto3
        except ImportError as e:
            raise S3NotConfigured("the `boto3` package is not installed") from e
        return boto3.client(
            "s3",
            region_name=s.s3_region or None,
            endpoint_url=s.s3_endpoint_url or None,
        )

    # V1 fills these. Defined now so the protocol contract is complete.
    def put(self, *, key: str, data: bytes, content_type: str) -> StorageRef:  # pragma: no cover
        client = self._client()
        client.put_object(
            Bucket=get_settings().s3_bucket, Key=key, Body=data, ContentType=content_type
        )
        return StorageRef(backend=self.name, key=key)

    def signed_url(self, ref: StorageRef, *, expires_s: int = 3600) -> str:  # pragma: no cover
        client = self._client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": get_settings().s3_bucket, "Key": ref.key},
            ExpiresIn=expires_s,
        )

    def delete(self, ref: StorageRef) -> None:  # pragma: no cover
        self._client().delete_object(Bucket=get_settings().s3_bucket, Key=ref.key)
