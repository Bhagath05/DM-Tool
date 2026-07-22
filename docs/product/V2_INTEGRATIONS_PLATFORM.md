# Version 2 — Production Integrations Platform (V2 Priority #1)

> **STATUS: ROADMAP + ARCHITECTURE ONLY. DO NOT IMPLEMENT UNTIL V1.0 SHIPS.**
> Feature-frozen. This captures the Integrations Platform request as an
> audit-first plan that **extends the existing `integrations` module** — it is
> not a rebuild. Real OAuth is gated on per-provider developer-app credentials
> the release owner must provision; nothing here is built with fake APIs.

## The architecture already exists — V2 extends it, never rebuilds it
A code audit of `aicmo/modules/integrations/` shows the exact provider
architecture the request describes is already in place:

| Requested piece | Already exists |
|---|---|
| Uniform provider interface | `providers/base.py::IntegrationProvider` (ABC): `authorize_url` · `exchange_code` · `refresh` · `fetch_account_info` · `sync` · `info` |
| "Add an integration = a few files" | `registry.py::IntegrationRegistry` — providers self-register by `slug` on import |
| Encrypted tokens, never exposed | `crypto.py` + `social/token_crypto.py` + `IntegrationCredential` (encrypted at rest via `INTEGRATION_TOKEN_KEY`; prod boot-guard requires it) |
| OAuth state / CSRF | `oauth_state.py`, `state.py` (state validation) |
| Connection status + last sync + errors | `IntegrationConnection` (state, scopes_granted, connected_at, last_sync_at, last_error_at, error_message) |
| Sync logs / events | `IntegrationEvent` |
| Retry | `http_retry.py` |
| Unified data types | `OAuthTokens`, `AccountInfo`, `SyncResult`, `ProviderInfo` |
| Concrete providers (12) | youtube, linkedin, linkedin_organic, google_business_profile, facebook_pages, hubspot, meta_ads, salesforce, google_ads, pinterest, tiktok, organic |

**Implication:** V2 = (a) add the missing providers by implementing the ABC +
self-registering, (b) extend the ABC + workers for the richer capabilities
below, (c) build the connected-dashboard UI. All on top of what exists.

## Integration coverage — 35 requested, mapped honestly
✅ exists · ⚠️ partial (organic vs ads, or lives elsewhere) · ❌ new provider

- **Publishing:** Facebook Pages ✅ · LinkedIn ✅ · YouTube ✅ · Pinterest ✅ · Google Business Profile ✅ · Instagram Business ⚠️ (via Meta graph — add)
- **Advertising:** Meta Ads ✅ · Google Ads ✅ · TikTok ⚠️ (organic exists; Ads = extend) · LinkedIn Ads ⚠️ (organic exists; Ads = extend)
- **CRM:** HubSpot ✅ · Salesforce ✅
- **Commerce:** Stripe ⚠️ (in `billing/`; expose as read integration) · Shopify ❌ · WooCommerce ❌ · Razorpay ❌
- **Analytics:** GA4 ❌ · Search Console ❌ · GTM ❌ · Meta Pixel ❌ · TikTok Pixel ❌ · Clarity ❌ · Hotjar ❌
- **Communication:** Mailchimp ❌ · Klaviyo ❌ · Brevo ❌ · WhatsApp Business ❌ *(email send provider `Resend` already exists for transactional)*
- **Automation:** Slack ❌ · Discord ❌ · Zapier ❌ · Make ❌ · Airtable ❌ · Notion ❌

Net: ~11 exist/partial, ~24 net-new providers — **each is "implement the ABC +
register," the modularity already delivered.**

## V2 delta — what's genuinely new (extend, don't fork)
1. **Extend `IntegrationProvider` ABC** with the capabilities the request adds
   and the base doesn't yet formalize: `disconnect()`, `verify_permissions()`,
   `health()`, `publish()`, `fetch_analytics()`, `handle_webhook()`. Keep them
   as ABC methods so every provider stays uniform — no per-provider branching.
2. **Webhook ingestion** — signed-webhook endpoint + per-provider signature
   verification + replay protection. (New; `IntegrationEvent` can store them.)
3. **Background workers** (reuse the Arq worker, not a new one): daily sync,
   manual sync, analytics refresh, token refresh, webhook processing, **retry
   queue + dead-letter queue**. Token-refresh + retry patterns partly exist
   (`http_retry.py`, `refresh()`).
4. **Unified AI-facing schema** — one normalized shape (audience / performance /
   creative / campaign / revenue / conversions / comments / reviews / search /
   profile) that every provider's `sync()` writes, so the Creative Intelligence
   Engine (V2 #2) consumes one format regardless of source.
5. **Connected-dashboard UI** — replace the current cards with rich per-provider
   dashboards (status, capabilities, metrics, permissions, last sync, logs;
   Connect / Reconnect / Disconnect / Test / Sync Now / View Logs). Use the
   existing design system; no placeholder metrics — render only real synced data
   (empty states until first sync).
6. **New providers (~24)** — one file each implementing the extended ABC.

## Hard gates (release owner)
- **Per-provider developer apps** (client ID/secret, redirect URIs, scopes, and
  **production app review** for Meta/Google/LinkedIn/TikTok). Each provider goes
  live only when its app credentials exist. **This cannot be faked** — providers
  ship one at a time as credentials arrive.
- **Secrets** per provider stored as env (never committed), tokens encrypted via
  the existing `INTEGRATION_TOKEN_KEY` path.

## Security (mostly already enforced)
Encrypted tokens ✅ · OAuth state/CSRF ✅ · rate limiting ✅ (Postgres-backed) ·
audit logs ✅ · input validation ✅ (Pydantic). **Add for V2:** PKCE where the
provider supports it, signed-webhook verification + replay protection.

## Suggested build order (post-V1.0)
1. Extend the ABC (#1) + the unified schema (#4) — the contract everything else
   depends on.
2. Webhook ingestion (#2) + worker set incl. DLQ (#3).
3. Connected-dashboard UI (#5) over the providers that already exist (12) —
   proves the platform end-to-end before scaling breadth.
4. New providers (#6), **credential-gated**, starting with the simplest OAuth
   (Slack, Google family) and the highest-value (Instagram/Meta, Shopify).

## Gate
Implement nothing until V1.0 is production-ready and verified. Then this is
**V2 Priority #1**, ahead of the Creative Intelligence Engine (which consumes
this platform's unified data).
