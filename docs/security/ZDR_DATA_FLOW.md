# ZDR / data-flow inventory (Phase 7B)

**Honest scope note.** This document does **not** claim "100% Zero Data
Retention." ZDR is a per-processor property that must be *verified and enabled*
per contract. Below is the actual data flow with each processor's retention /
training / deletion posture and what must be configured to reach the strongest
available privacy stance. Rows marked **VERIFY** require confirming the current
provider policy + enabling an enterprise/DPA control before any ZDR claim.

## What DM Tool minimizes by design
- **No raw LLM prompts/responses are persisted** to our DB — the LLM router
  records **token counts only**; we store *structured results* (strategy JSON,
  recommendations), never transcripts (`aicmo/llm/`).
- **No secrets in prompts.** Advisor/analytics prompts are built from computed
  evidence + business profile only — never tokens, keys, or credentials
  (pinned across advisor/marketing-analytics tests).
- **Tokens encrypted at rest** (Fernet, `integrations/crypto.py`;
  `social/token_crypto.py`) — never logged.
- **Sentry scrubbing**: `send_default_pii=False` + `before_send`/breadcrumb
  scrubbers strip secrets/tokens/keys + sensitive headers
  (`observability/sentry.py`).
- **Media** is private S3 + short-lived presigned URLs; bytes never in the DB.

## Processor matrix

| Processor | Purpose | Data sent | Personal data | Media | Prompt | Response stored by us | Provider retention | Training use | Deletion | Config to harden | ZDR/DPA status | Risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **AWS S3** | Media storage (our bucket) | Generated/uploaded media bytes | Possibly (user media) | Yes | No | Ref only (key) | Until we delete / lifecycle | No | `DeleteObject` + lifecycle | BPA, SSE, TLS-only, IAM least-priv | We control it. DPA: AWS DPA | Low |
| **Clerk** | Authentication / identity | Email, name, session | **Yes** | No | No | User id + email in `users` | Per Clerk plan | No | Delete user via Clerk + purge tenant | DPA in place; production keys | Auth data must be retained (not ZDR by nature) | Low–Med |
| **Sentry** | Error/telemetry | Stack traces, tenant tags (scrubbed) | Minimized | No | No | No (sent to Sentry) | Per plan retention | No | Data scrubbing + retention window | `send_default_pii=False` + scrubbers (done) | DPA available | Low |
| **OpenAI API** (default LLM) | Marketing reasoning | Business profile + computed evidence prompt | Possibly (business text) | No | **Yes** | Structured result only | **Default: not trained on; abuse-monitoring retention (short, e.g. ~30d)** | No (API default) | — | **VERIFY** current policy; enable **ZDR/enterprise** for eligible accounts | **VERIFY / enable ZDR** | Med |
| **Anthropic API** | LLM (if `llm_default_provider=anthropic`) | Same prompt shape | Possibly | No | **Yes** | Structured result only | Not trained on by default; retention per policy | No (default) | — | Enterprise/zero-retention options | **VERIFY** | Med |
| **Google Gemini API** (`google_api_key`) | LLM (if selected) | Same prompt shape | Possibly | No | **Yes** | Structured result only | **Free tier may be used to improve; paid API differs** | **VERIFY (tier-dependent)** | — | Use paid/Vertex, not free tier | **VERIFY — avoid free tier for prod** | Med–High if free tier |
| **Vertex AI Veo** (video, `veo3`) | Video generation | Text prompt (+ optional ref image) | Possibly | Output only | **Yes** | Ref only (S3) | Enterprise; configurable | No (Vertex enterprise default) | Provider deletion | Vertex DPA + region controls | **VERIFY DPA/region**; ships dark by default | Med |
| **OpenAI Images** | Image generation | Text prompt | Possibly | Output only | **Yes** | Ref only (S3) | Per API policy | No (API default) | — | Same as OpenAI API | **VERIFY** | Med |
| **Facebook / Meta** | OAuth read + publish | OAuth-scoped reads; post content on publish | Page/account data | Published media | No | Metrics + post id | Meta retains platform data | Per Meta policy | Delete post on platform | Least OAuth scopes | Platform-inherent retention (not ours) | Med |
| **YouTube / Google** | OAuth read + publish | Channel/video stats; uploads on publish | Channel data | Published media | No | Metrics + video id | Google retains platform data | Per Google policy | Delete video on platform | Least OAuth scopes | Platform-inherent | Med |
| **LinkedIn** | OAuth read + publish | socialActions reads; posts on publish | Org/page data | Published media | No | Metrics + post urn | LinkedIn retains | Per policy | Delete post | Least OAuth scopes | Platform-inherent | Med |
| **Pinterest** | OAuth read + publish | Pin analytics; pins on publish | Account data | Published media | No | Metrics + pin id | Pinterest retains | Per policy | Delete pin | Least OAuth scopes | Platform-inherent | Med |
| **Resend** (email, optional) | Transactional email | Recipient + body | **Yes** | No | No | Email log metadata | Per plan | No | Provider deletion | Off unless `EMAIL_PROVIDER=resend` | DPA available | Low (off by default) |

## Honest gaps / actions before a ZDR claim
1. **LLM (OpenAI/Anthropic/Google)** — confirm the *current* retention/training
   policy for the configured `llm_default_provider` and **enable ZDR /
   enterprise zero-retention** where the account is eligible. Do **not** use the
   Gemini free tier in production (it may be used for product improvement).
2. **Video (Vertex Veo)** — confirm the Vertex DPA + processing region and
   retention before enabling `video_enabled=true`. Ships dark today.
3. **Social platforms** — their retention is inherent to using their APIs and is
   **out of our control**; we minimize by requesting least OAuth scopes and
   storing only ids + metrics. This is disclosed, not "ZDR".
4. **Clerk / Sentry** — sign DPAs; keep Sentry retention short; PII stays
   minimized + scrubbed. Auth identity is retained by necessity.

## Deletion / retention on our side
- **Asset delete** → `S3Backend.delete` + row removal (keys orphaned objects to
  lifecycle expiry).
- **Account/tenant delete** → `orgs/service.reset_organization_data` /
  `purge_organization` remove tenant rows (metrics, assets, recommendations,
  publishing records). Object bytes are then lifecycle-expired.
- **No raw AI transcripts retained** (see top). Backups follow the managed
  Postgres provider's snapshot retention (document + bound per plan).

---

## Phase 8 — verification status (supersedes the "VERIFY" wording above)

**Verification date:** not yet performed (staging validation not run — no live
infra in the current environment). **No blanket ZDR claim is made.**

**Status vocabulary (use exactly these):**
- **VERIFIED** — confirmed against the provider's current policy/DPA + our config.
- **PARTIALLY VERIFIED** — some controls confirmed; others outstanding.
- **REQUIRES ENTERPRISE CONFIGURATION** — the required posture exists but must be
  enabled on an enterprise/DPA plan we have not yet activated.
- **UNKNOWN — NEEDS HUMAN VERIFICATION** — not yet confirmed; must not be treated
  as VERIFIED. *Never convert UNKNOWN → VERIFIED without evidence + a date.*

| Processor | Status | Confidence | Notes / action before a claim |
|---|---|---|---|
| AWS S3 (our bucket) | **PARTIALLY VERIFIED** | High | Code: SSE + private + bounded URLs pinned by tests. Bucket BPA/TLS-policy/IAM-OIDC = **config not yet applied** (staging). |
| Render (host) | **UNKNOWN — NEEDS HUMAN VERIFICATION** | Med | Hosts app + DB + Redis + OIDC broker. Confirm Render DPA + data region + log retention; confirm OIDC issuer/aud/sub values. |
| Clerk (auth) | **REQUIRES ENTERPRISE CONFIGURATION** | Med | PII processor by nature (auth). Sign DPA; keep retention minimal. Not ZDR (identity must persist). |
| Sentry | **PARTIALLY VERIFIED** | High | `send_default_pii=False` + secret/header scrubbers in code (verified). Confirm DPA + retention window on the staging project. |
| OpenAI API (default LLM) | **REQUIRES ENTERPRISE CONFIGURATION** | Med | API default: not trained on; short abuse-retention. Enable **ZDR/enterprise** for eligible accounts + confirm current policy/date. |
| Anthropic API | **REQUIRES ENTERPRISE CONFIGURATION** | Med | Not trained on by default; confirm zero-retention/enterprise option + date. |
| Google Gemini API | **UNKNOWN — NEEDS HUMAN VERIFICATION** | Low | **Free tier may be used for improvement** → do not use free tier in prod. Confirm paid/Vertex posture. |
| Vertex AI **Veo** (video) | **REQUIRES ENTERPRISE CONFIGURATION** | Med | Enterprise; configurable retention + region. Confirm DPA + region before `video_enabled=true`. Ships dark today. |
| OpenAI Images | **REQUIRES ENTERPRISE CONFIGURATION** | Med | Same as OpenAI API. |
| Facebook/Meta | **UNKNOWN — NEEDS HUMAN VERIFICATION** | Low | Platform-inherent retention (their platform, not ours). Minimize scopes; disclose. |
| YouTube/Google | **UNKNOWN — NEEDS HUMAN VERIFICATION** | Low | Same — platform-inherent. |
| LinkedIn | **UNKNOWN — NEEDS HUMAN VERIFICATION** | Low | Same — platform-inherent. |
| Pinterest | **UNKNOWN — NEEDS HUMAN VERIFICATION** | Low | Same — platform-inherent. |

**Application-side guarantees (VERIFIED in code, independent of provider policy):**
no raw LLM prompts/responses persisted; no secrets in prompts; tokens encrypted
+ never logged; Sentry scrubbed; media private + bounded URLs. These hold
regardless of the rows above.
