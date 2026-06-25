# Phase 1 — Stripe Billing + Usage Metering

> Turns the existing billing scaffold into live, metered revenue.
> Design only. No code until approved.

---

## Why this is mostly "finish the scaffold"

The schema and service layer were **built Stripe-ready** in Phase 10.2e:
- `subscription` already has `external_subscription_id`,
  `external_customer_id`, `plan_slug`, `status`, period + cancel fields.
- `invoice` already has `external_invoice_id` (unique), `hosted_invoice_url`,
  `amount_total_cents`, `currency`, `status`, `paid_at`.
- `record_usage()` exists as **"the ONLY write path to usage_event"** — but
  is currently **never called** from any generator.
- `get_usage_summary()` already compares counts against
  `plan_catalog.quota_for(plan, kind)` — enforcement logic is half-built.
- `plan_catalog.py` note: *"When Stripe lands, prices move to Stripe price
  ids + a server-side resolver. The interface stays the same."*

So Phase 1 = (a) wire Stripe to the existing external-ID columns, (b) start
calling `record_usage`, (c) add a quota gate. No rewrite.

---

## 1. Technical design

### 1.1 Dark-launch flags (ship safely)
Two new flags in `config.py`, both default **false** — so this entire
phase ships dormant and is enabled per-environment:
- `billing_live_enabled` — when false, checkout/portal keep returning the
  existing "honest placeholder" upgrade-request flow (zero behavior change).
- `billing_enforce_limits` — when false, usage is **recorded but never
  blocks** (observe-before-enforce). Early Access stays unlimited regardless.

### 1.2 Stripe gateway adapter
`aicmo/modules/billing/payments/stripe_gateway.py` — a thin, stubbable
wrapper over the `stripe` SDK:
- `create_or_get_customer(org)` → `external_customer_id`
- `create_checkout_session(org, plan_slug, success_url, cancel_url)` → URL
- `create_billing_portal_session(org, return_url)` → URL
- `construct_event(payload, sig_header)` → verified Stripe event (raises on
  bad signature)

Plan→price mapping lives in the **catalog** (code), not the DB:
`stripe_price_id` added to `PlanDescriptor` (read from config env per
plan). Interface (`get_catalog`, `quota_for`) unchanged — frontend
untouched.

### 1.3 New endpoints
| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/v1/billing/checkout` | `require_permission("billing.manage")` (owner) | create Checkout Session → return redirect URL |
| POST | `/api/v1/billing/portal` | `require_permission("billing.manage")` | open Stripe Billing Portal |
| POST | `/api/v1/billing/webhooks/stripe` | **public** (signature-gated) | sync subscription/invoice from Stripe |

When `billing_live_enabled=false`, checkout/portal return `409` with the
existing placeholder payload, so the UI behaves exactly as today.

### 1.4 Webhook → DB sync (idempotent)
Public router (no tenant header — mirrors the Clerk webhook pattern).
Verify `Stripe-Signature` via `construct_event`; **drop unverified**.
Handled events → existing columns:
| Stripe event | Effect |
|---|---|
| `checkout.session.completed` | set `external_customer_id` + `external_subscription_id`, plan_slug, status=active |
| `customer.subscription.updated` | sync plan_slug, status, period_start/end, cancel_at_period_end |
| `customer.subscription.deleted` | status=canceled, canceled_at |
| `invoice.paid` | upsert `invoice` row (external_invoice_id unique), paid_at, hosted_invoice_url |
| `invoice.payment_failed` | invoice status=open/past_due; (Phase-2 notification hook) |

Org is resolved from `external_customer_id` → the `subscription` row.
Idempotency via a new `stripe_event` log (event id unique) — a re-delivered
event is a no-op.

### 1.5 Usage metering
- **Emit:** call the existing `record_usage(session, org, kind, ...)` at
  generation sites (content/ads/visuals/campaigns/bundles + csv upload +
  lead processed). Best-effort, same transaction as the asset write —
  identical pattern to the AI-audit hook already added there.
- **Enforce:** a `check_quota(session, org, kind)` gate called *before*
  generation. `None` limit (Early Access) → always allowed. Over limit +
  `billing_enforce_limits=true` → raise `402 Payment Required` with an
  upgrade CTA payload. Off → record-only.
- New usage kinds (`content_generated`, `ad_generated`, `visual_rendered`,
  `campaign_generated`) added to the catalog + the `usage_event.kind` CHECK.

---

## 2. Database impact

**Additive only. Migration `0033_billing_live`.**
- **No change** to `subscription`/`invoice` — external-ID columns already
  exist (the whole point).
- **New** `stripe_event` table (webhook idempotency): `event_id` (PK/unique),
  `type`, `organization_id` (nullable — resolved when possible), `received_at`,
  `processed_at`. Small, append-only.
- **Extend** `usage_event.kind` CHECK to add the 4 new generation kinds.
- Plan price ids → **config/catalog (code)**, not DB. No column.
- New indexes: `usage_event (organization_id, kind, occurred_at)` for the
  quota-count query (complements 0031).
- All reversible. `subscription`/`invoice` data untouched on downgrade.

RLS readiness: `stripe_event` is account-level idempotency, not tenant
data — excluded from RLS (documented). `usage_event` is already
tenant-scoped + RLS-ready.

---

## 3. APIs affected

- `billing` router: **+3 endpoints** (checkout, portal, webhook). Existing
  GET plans/subscription/usage/invoices + POST upgrade-request **unchanged**.
- Generation endpoints (content/ads/visuals/campaigns/bundles): gain a
  **pre-generation quota check**. Backward compatible — Early Access is
  unlimited, and enforcement is flag-gated (off by default), so current
  users see no change. When a paid org is over limit (and enforcement on),
  they get a clean `402` with an upgrade path, not a 500.
- OpenAPI gains the 3 endpoints + a `402` response shape. No breaking
  changes to existing contracts.

---

## 4. Security impact

- **Stripe webhook signature verification is mandatory** — unverified
  payloads are dropped (mirrors the Clerk Svix pattern). The webhook is the
  only public surface and it's HMAC-gated.
- **No card data ever touches our DB.** Checkout + Billing Portal are
  Stripe-hosted → PCI scope stays at SAQ-A (minimal). We store only opaque
  external IDs + hosted invoice URLs.
- New secrets `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` → added to
  `docs/security/SECRETS.md` (inventory + rotation) and to
  `validate_production_secrets()` (required in prod **only when
  `billing_live_enabled=true`** — so non-billing prod deploys still boot).
- checkout/portal require `billing.manage` (Owner) — a viewer can't start a
  subscription or open the portal.
- Webhook idempotency (`stripe_event`) prevents replay-driven double-writes.
- `usage_event` already tenant-scoped + RLS-ready; the quota gate reads
  only the caller's org.
- Gitleaks rule for `sk_live_`/`whsec_` already exists (`.gitleaks.toml`).

---

## 5. Rollback plan

Ships dark; multiple independent off-switches:
- **`billing_live_enabled=false`** (default) → checkout/portal revert to the
  existing placeholder flow. The product behaves exactly as today.
- **`billing_enforce_limits=false`** (default) → usage is recorded but never
  blocks a generation. Decouples "start measuring" from "start enforcing."
- **Webhook problem** → flip `billing_live_enabled` off; the webhook still
  verifies + logs but stops mutating subscriptions. `subscription` rows are
  unaffected; Early Access lazy-provision keeps the Billing page working.
- **Migration 0033** is reversible (drops `stripe_event`, reverts the CHECK,
  drops the index). `subscription`/`invoice` rows are never touched.
- **Stripe-side:** subscriptions can be managed/refunded in the Stripe
  dashboard independently of our app.

Escalation ladder: flag off → (if needed) revert router → (last) downgrade
0033. No data loss at any rung.

---

## 6. Success metrics

**Revenue / conversion**
- First paid conversion; MRR; checkout-session completion rate; trial→paid.

**Reliability / correctness**
- 100% of processed webhooks signature-verified; 0 unverified processed.
- Webhook idempotency: re-delivered events cause 0 duplicate rows.
- Subscription state in our DB matches Stripe (reconciliation check).

**Metering**
- Usage recorded for ≥99% of generations (sampled vs AI-audit count).
- % orgs approaching/over limit (informs pricing); 0 false-positive blocks
  for Early Access.

**Safety**
- 0 card-data fields in our schema (audit).
- 0 generation 500s caused by the quota gate (it must fail-open to allow).

---

## 7. Reuse map (no rewrites)

| Reused | From |
|---|---|
| `subscription` / `invoice` external-ID columns | migration 0027 (built Stripe-ready) |
| `record_usage` (single write path) | `billing/service.py` |
| `get_usage_summary` + `quota_for` | `billing/service.py`, `plan_catalog.py` |
| `ensure_subscription` lazy-provision | `billing/service.py` |
| Webhook public-router + signature pattern | `auth/clerk_webhook.py`, `modules/security` |
| Secret runbook + boot guard + gitleaks rules | Phase S1 |
| `usage_event` tenant scope + RLS readiness | TenantMixin + Phase-RLS |
| AI-audit hook placement (where to call record_usage) | `record_ai_generation` sites |

## 8. Task breakdown (for execution after approval)

1. `config.py` — flags + Stripe secrets + per-plan price-id env.
2. Migration `0033_billing_live` — `stripe_event`, usage `kind` CHECK,
   usage index.
3. `payments/stripe_gateway.py` (+ stub for tests).
4. `billing/service.py` — checkout/portal/webhook-sync + `check_quota`.
5. `billing/router.py` — +3 endpoints; webhook on a public router.
6. Wire `record_usage` + `check_quota` into the 5 generation services.
7. `plan_catalog.py` — add `stripe_price_id` + new usage kinds.
8. `main.py` — register the billing webhook public router.
9. `validate_production_secrets` + `SECRETS.md` — Stripe keys.
10. Tests — webhook signature + idempotency, checkout perm-gate, quota gate
    (unlimited Early Access, enforce on/off), migration reversibility.
11. Gates: pytest + typecheck + (frontend billing page still renders).

## 9. Open product decisions (need your call before/along with build)
- **Plan limits** for `growth`/`scale` (the actual quota numbers) — product
  pricing decision. Default: keep Early Access unlimited; set placeholder
  numbers for growth/scale until pricing is finalized.
- **Trial**: offer a Stripe trial period on `growth`? (default: no trial).
- **Annual vs monthly** price ids (default: monthly only to start).
