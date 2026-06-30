# Object Storage (Media Backend) — Production Deployment Guide

DM Tool stores user-generated binary assets (rendered images, videos, design
exports) behind a pluggable **storage backend**. Postgres only ever stores a
`StorageRef` (`backend` + `key`); the bytes live behind the backend, reached
only through short-lived signed URLs.

The backend is selected **entirely by environment variables** — no provider is
hardcoded. There are two implementations of the same protocol:

| `MEDIA_BACKEND` | Implementation | Use |
|---|---|---|
| `local` (default) | `LocalDiskBackend` — writes to `MEDIA_DIR` | Local dev + staging only |
| `s3` | `S3Backend` (boto3) | Any AWS-S3-compatible store |
| `r2` | `S3Backend` (boto3) | Cloudflare R2 (S3 API via a custom endpoint) |

> `s3` and `r2` use the **same** code path. `r2` is just the conventional value
> to make it obvious in the dashboard that the bucket is Cloudflare R2.

---

## Why local storage is unsafe in production

`MEDIA_BACKEND=local` writes files to the container's local disk. On our
production host (Render) that is fatal for two reasons:

1. **Ephemeral filesystem.** The disk is wiped on every deploy, restart, and
   (on the free tier) idle spin-down. Any asset written to local disk is
   **permanently lost** the next time the container cycles.
2. **Not shared across services.** `web` and `worker` are separate Render
   services with separate filesystems. An image rendered by the `worker` is
   written to the worker's disk and is **unservable** by the `web` service —
   the signed URL resolves to a file that does not exist there.

Because of this, the application enforces a **production-safety gate**:

> When `MEDIA_BACKEND=local` **and** `API_ENV=production`,
> `Settings.media_persistence_available` is `False`.

While that gate is active:

- **Image generation is disabled.** Any code path that would persist an image
  raises `MediaPersistenceUnavailable`, which a global handler maps to a clear
  **HTTP 409** (`code: "object_storage_required"`) — never a silent success.
- **Asset exports requiring a persisted file are disabled** the same way.
- **Everything else keeps working**: text/strategy generation, AI copy,
  natural-language and structured **design editing**, **revision history**, and
  every non-file workflow — these live in Postgres and never touch storage.
- **`GET /api/v1/system/storage`** reports the capability so the UI can show an
  **admin-only** notice and disable the affected controls.

**We never silently lose an asset.** The local backend refuses the write and
fails loudly instead of orphaning the file. The gate lifts automatically the
moment a durable backend is configured — no code change.

> Staging (`API_ENV=staging`) deliberately allows `local` so the demo
> environment runs without a bucket. The gate is production-only.

---

## How to configure Cloudflare R2

You need a Cloudflare account. R2 has no egress fees and speaks the S3 API.

1. **Create a bucket.** Cloudflare dashboard → R2 → *Create bucket*
   (e.g. `dmtool-media-prod`). Pick a location hint near your users.
2. **Create an API token.** R2 → *Manage R2 API Tokens* → *Create API token*:
   - Permissions: **Object Read & Write**
   - Scope: the single bucket above (least privilege — do not grant account-wide)
   - Save the **Access Key ID** and **Secret Access Key** (shown once).
3. **Find your S3 endpoint.** It looks like
   `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
4. Keep the bucket **private** (no public access). DM Tool serves assets only
   through application-signed URLs; the bucket itself must never be public.

---

## Required environment variables

Set these on **both** the `web` and `worker` services (the worker renders
assets; the web service serves them):

| Variable | Example | Notes |
|---|---|---|
| `MEDIA_BACKEND` | `r2` | Selects the S3-compatible backend |
| `S3_BUCKET` | `dmtool-media-prod` | Bucket name |
| `S3_REGION` | `auto` | R2 ignores region; use `auto` |
| `S3_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` | R2 S3 endpoint |
| `AWS_ACCESS_KEY_ID` | `<R2 access key id>` | boto3 default credential chain |
| `AWS_SECRET_ACCESS_KEY` | `<R2 secret>` | boto3 default credential chain |
| `MEDIA_SIGNING_SECRET` | `<random 32+ bytes>` | HMAC secret for signed media URLs (already required) |

> Credentials are read by boto3's standard credential chain — set
> `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` as secrets. They are **not**
> committed and **not** in `render.yaml`.

The production boot guard refuses to start if `MEDIA_BACKEND` is `s3`/`r2` but
`S3_BUCKET` is missing — so a half-configured deploy fails fast instead of
silently degrading.

---

## Bucket permissions

- **Private bucket.** No public-read. No anonymous access. No public bucket URL.
- **Scoped token.** The API token grants Object Read & Write on **only** this
  bucket. Rotate it independently of other secrets.
- **App-mediated access only.** Clients never receive raw bucket URLs — only
  time-limited signed URLs minted by the API.

---

## CORS configuration

Asset bytes are fetched **browser → signed URL** (R2/S3), so the bucket needs a
CORS policy allowing GET from the frontend origin. In the Cloudflare R2 bucket
settings → *CORS policy*:

```json
[
  {
    "AllowedOrigins": ["https://dm-tool-web.vercel.app"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["Content-Length", "Content-Type"],
    "MaxAgeSeconds": 3600
  }
]
```

- Add every frontend origin you serve from (production domain, preview domains).
- Only `GET`/`HEAD` are needed — uploads go **server-side** (worker → R2), never
  directly from the browser, so no `PUT` origin is required.

---

## Migration steps: LOCAL → R2

There is **no data to migrate** while local-in-production is gated (no assets
were ever persisted). This is a forward cut-over:

1. Create the R2 bucket + API token (above).
2. Apply the CORS policy.
3. Add the env vars on **both** `web` and `worker`.
4. Set `MEDIA_BACKEND=r2` on both services.
5. Redeploy. On boot, `media_persistence_available` becomes `True`; the 409 gate
   lifts automatically.
6. **Only now** enable Creative Studio image features (separate, deliberate
   step): `STUDIO_ENABLED=true` (Render) + `NEXT_PUBLIC_STUDIO_ENABLED=true`
   (Vercel). Storage and the feature flag are independent — never enable the
   flag while the gate is active.

If you ever migrate from one durable backend to another with existing assets,
copy objects first (e.g. `rclone copy s3:old r2:new`), then flip `MEDIA_BACKEND`.

---

## Rollback procedure

To revert (e.g. R2 misconfiguration):

1. **Disable the image features first** so no new writes are attempted:
   `STUDIO_ENABLED=false` (Render) + `NEXT_PUBLIC_STUDIO_ENABLED=false` (Vercel).
2. Set `MEDIA_BACKEND=local` on both services and redeploy. The production gate
   re-engages: image generation + exports return the clear 409; all non-file
   workflows keep working. No data is lost or corrupted (the gate prevents
   ephemeral writes).
3. Investigate, fix the R2 config, then re-run the migration steps.

> Never roll back to `local` in production **while** the Studio image flag is
> on — disable the flag first so users see the admin notice instead of 409s.

---

## Validation checklist

After setting `MEDIA_BACKEND=r2`, before enabling image features:

- [ ] `web` and `worker` both have `MEDIA_BACKEND`, `S3_BUCKET`, `S3_REGION`,
      `S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
      `MEDIA_SIGNING_SECRET`.
- [ ] Both services booted successfully (no `S3_BUCKET is missing` fatal).
- [ ] `GET /api/v1/system/storage` returns
      `{"media_backend":"r2","media_persistence_available":true,
      "image_generation_enabled":true,"asset_exports_enabled":true}`.
- [ ] Bucket is **private** (no public access).
- [ ] CORS policy lists every frontend origin; a browser can GET a signed URL
      without a CORS error.
- [ ] API token is scoped to this one bucket.
- [ ] Round-trip: generate an asset → it persists → its signed URL serves the
      bytes → it still serves after a redeploy/restart (proves durability).
- [ ] Only after all green: enable `STUDIO_ENABLED` + `NEXT_PUBLIC_STUDIO_ENABLED`.

---

## Reference — where this lives in the code

- Backend selection: `apps/api/aicmo/modules/creative/storage/registry.py`
- Storage protocol + `MediaPersistenceUnavailable`: `…/storage/base.py`
- Local backend + write backstop: `…/storage/local.py`
- S3/R2 backend (boto3): `…/storage/s3.py`
- Capability flag: `Settings.media_persistence_available` in `apps/api/aicmo/config.py`
- 409 handler + `GET /api/v1/system/storage`: `apps/api/aicmo/main.py`
