# AWS S3 media storage — production hardening (Phase 7B)

DM Tool stores generated/uploaded media bytes in an S3-compatible object store
and keeps **only a `StorageRef` (backend + key) in Postgres — never bytes**
(`aicmo/modules/creative/storage/`). This doc is the ops runbook for making that
store production-safe. **Nothing here is applied automatically** — it is bucket +
IAM configuration you perform in AWS before enabling `MEDIA_BACKEND=s3`.

## Selection & credentials
- Enable with `MEDIA_BACKEND=s3` + `S3_BUCKET` (+ `S3_REGION`). Leave
  `S3_ENDPOINT_URL` empty for AWS.
- **Credentials: short-lived, role-based — NO long-lived static keys.**
  Production runs on Render, which supports **managed AWS OIDC**: Render
  presents an OIDC identity token, AWS STS `AssumeRoleWithWebIdentity`
  exchanges it for **short-lived rotating credentials** for a least-privilege
  IAM role. boto3's **default credential chain** picks these up automatically
  from `AWS_ROLE_ARN` + `AWS_WEB_IDENTITY_TOKEN_FILE` (set by Render's OIDC
  integration). `S3Backend._client()` passes only `region_name`/`endpoint_url`
  and **never** reads/constructs `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
  / `AWS_SESSION_TOKEN` (pinned by
  `test_no_static_aws_keys_passed_to_client` +
  `test_client_relies_on_default_credential_chain_no_static_or_session_keys`).
  → **No code change was needed for OIDC** — the client was already
  default-chain-based. Do **not** set static AWS keys on the Render services.
  Local dev may use a normal AWS profile/SSO; production must be OIDC-only.

### Render OIDC → STS trust relationship (attach to the app role)
Create the least-privilege role (below) with this **trust policy**, federating
Render's OIDC provider. Fill in Render's OIDC issuer URL + the audience/subject
Render documents for your service (verify against Render's current OIDC docs —
mark **UNKNOWN — NEEDS HUMAN VERIFICATION** until confirmed):
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/OIDC_ISSUER_HOST" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "OIDC_ISSUER_HOST:aud": "RENDER_AUDIENCE",
        "OIDC_ISSUER_HOST:sub": "RENDER_SERVICE_SUBJECT"
      }
    }
  }]
}
```
Scope `sub` to the specific Render service(s) that need S3 (API + worker) — not
a wildcard. Keep infrastructure/deploy admin on a **separate** principal; the
runtime app role never gets IAM/bucket admin.

## Bucket configuration (do this in AWS, once)
1. **Block Public Access** — enable all four settings at the bucket (and
   account) level. The bucket is never public; access is only via short-lived
   presigned URLs.
2. **Default encryption** — SSE-S3 (AES256) or SSE-KMS as the bucket default.
   The app *also* sets `ServerSideEncryption=AES256` on every `PutObject`
   (belt-and-suspenders; pinned by `test_put_encrypts_at_rest`).
3. **TLS-only bucket policy** — deny any request where
   `aws:SecureTransport = false`:
   ```json
   { "Effect": "Deny", "Principal": "*", "Action": "s3:*",
     "Resource": ["arn:aws:s3:::YOUR_BUCKET", "arn:aws:s3:::YOUR_BUCKET/*"],
     "Condition": { "Bool": { "aws:SecureTransport": "false" } } }
   ```
4. **Versioning** (optional) + **object ownership = Bucket owner enforced**
   (disables ACLs — access is IAM-only).

## Encryption (SSE-S3 now; SSE-KMS as a documented future upgrade)
- The app writes every object with **SSE-S3 (AES256)** today; pair with bucket
  default encryption. **Never SSE-C** (the storage abstraction hands bytes to
  boto3, not customer-managed keys, so SSE-C would break the layer).
- **SSE-KMS is a clean, non-breaking upgrade** for enterprise/data-residency:
  set the bucket default to `aws:kms` with a CMK and grant the app role
  `kms:GenerateDataKey`/`kms:Decrypt` on that key — no storage-layer rebuild.
  Do **not** block the current staging rollout on SSE-KMS.

## IAM policy — least privilege (attach to the app role, assumed via OIDC)
The application needs exactly four object actions on the one bucket. **No**
bucket administration, no `s3:*`, no other buckets.
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DmToolMediaObjects",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:HeadObject"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET/*"
    }
  ]
}
```
(`ListBucket` is intentionally omitted — the app addresses objects by exact key,
never lists. Add it only if a future feature genuinely enumerates keys.)

## Presigned URLs
- Access is presigned-`GetObject` only; objects are otherwise private.
- **Expiry is clamped in code to [60s, 3600s]** (`S3Backend.signed_url` →
  `_clamp_expiry`, pinned by `test_presigned_url_expiry_is_bounded`) so no caller
  can mint a long-lived public link.
- **Authorization happens before issuance.** A URL is only produced after a
  brand-scoped DB fetch of the asset (e.g. `BrandAsset … WHERE brand_id = ?`),
  so a tenant can never obtain a URL for another tenant's object. Cross-tenant
  asset references inside designs are additionally blocked by
  `CrossTenantAssetRef` in the revision pipeline.

## Keys / tenant isolation
- Keys are **server-generated and tenant-scoped** — e.g.
  `brand_asset/{organization_id}/{uuid}`, `{organization_id}/{project_id}/reel.mp4`.
  **User-supplied filenames are never used** in a key → no path traversal / key
  injection.

## Upload validation (already enforced)
- Brand-asset uploads: content-type **allow-list** (PNG/JPEG/WebP/GIF/web-font;
  **SVG/HTML rejected** — script/XSS) + **10 MB** size bound + empty-file
  rejection (`creative/design/router.py`, `tests/creative/test_upload_safety.py`).
- Provider-generated **video** output is validated before persistence
  (content-type + size + MP4 `ftyp` signature) — `storage/validation.py`,
  `tests/creative/test_media_security.py`.

## Lifecycle & cost control (bucket lifecycle rules — configure in AWS)
- **Temp / failed / abandoned assets**: prefix these under a `tmp/` key space
  and set a lifecycle rule to expire objects after N days. (Today the pipeline
  marks failed renders `failed_rendering` and writes nothing on failure.)
- **Incomplete multipart uploads**: lifecycle rule to abort after 1 day.
- **Storage class transition**: transition rarely-accessed exports to
  Infrequent-Access after 30 days if cost warrants.
- **App-side**: the video pipeline has bounded per-user/day caps
  (`video_render_daily_cap`) and an org monthly budget; the storage layer
  dedupes by content (`CreativeAsset.checksum`).

## Deletion
- `S3Backend.delete` (`DeleteObject`) removes an object; `orgs/service.py`
  `reset_organization_data` / `purge_organization` remove a tenant's rows (which
  reference the keys) so orphaned objects can be lifecycle-expired.

## Verification checklist (staging first)
- [ ] Block Public Access = ON (bucket + account)
- [ ] Default encryption = ON
- [ ] TLS-only bucket policy attached
- [ ] Task role has the 4-action least-privilege policy only
- [ ] `MEDIA_BACKEND=s3`, `S3_BUCKET`/`S3_REGION` set; no static AWS keys
- [ ] A test upload → object encrypted (`x-amz-server-side-encryption: AES256`)
- [ ] Presigned URL works and expires within ≤1h
- [ ] Cross-tenant asset URL request fails closed
- [ ] Lifecycle rules for `tmp/` + incomplete multipart configured
