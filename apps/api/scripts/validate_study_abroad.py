#!/usr/bin/env python3
"""Validate the intelligence engine against a Study Abroad Consultancy profile.

Uses existing service-layer APIs only — no new integrations or features.
Seeds GlobalPath Study Abroad with historical Instagram content, GBP metrics,
leads, campaign CSV, and outcome history, then runs compose_intelligence and
generates production assets from recommendation context.

Usage (from apps/api, with Postgres running):
    python scripts/validate_study_abroad.py
    python scripts/validate_study_abroad.py --skip-assets   # intelligence only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "study_abroad"

GENERIC_PHRASES = (
    "post on social media",
    "post consistently",
    "improve seo",
    "boost engagement",
    "increase brand awareness",
    "create quality content",
    "be active on social",
    "optimize your profile",
)

REQUIRED_REC_FIELDS = (
    "observation",
    "root_cause",
    "recommended_action",
    "expected_impact",
    "confidence",
    "data_sources_used",
)


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[2]
        load_dotenv(root / ".env")
    except ImportError:
        pass


def _print_section(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(title)
    print("=" * 72)


def validate_recommendation_contract(rec, *, label: str) -> list[str]:
    """Return list of validation errors for one recommendation."""
    errors: list[str] = []
    for field in REQUIRED_REC_FIELDS:
        val = getattr(rec, field, None)
        if val is None or (isinstance(val, str) and len(val.strip()) < 10):
            errors.append(f"{label}: missing or too short `{field}`")
        if field == "confidence" and isinstance(val, int) and not 0 <= val <= 100:
            errors.append(f"{label}: confidence out of range ({val})")
    sources = getattr(rec, "data_sources_used", None) or []
    if not sources:
        errors.append(f"{label}: data_sources_used is empty")
    text = " ".join(
        str(getattr(rec, f, "") or "") for f in ("observation", "root_cause", "recommended_action")
    ).lower()
    for phrase in GENERIC_PHRASES:
        if phrase in text:
            errors.append(f"{label}: generic phrase detected — `{phrase}`")
    return errors


def validate_signal_coverage(ctx, report) -> list[str]:
    """Verify all four intelligence layers were loaded before compose."""
    errors: list[str] = []
    if not ctx.brain_complete:
        errors.append("Business Brain incomplete")
    if not ctx.outcome_context.get("recent_outcomes"):
        errors.append("No historical outcomes loaded")
    metrics = ctx.connector_context.get("metrics") or []
    ig = [m for m in metrics if m.get("provider", "").startswith("instagram")]
    gbp = [m for m in metrics if m.get("provider") == "google_business_profile"]
    if not ig:
        errors.append("No Instagram connector metrics in signal context")
    if not gbp:
        errors.append("No Google Business Profile metrics in signal context")
    if not ctx.activity_signals and not ctx.has_lead_intel:
        errors.append("No lead activity signals")
    return errors


def collect_recommendations(report) -> list[tuple[str, object]]:
    recs: list[tuple[str, object]] = []
    if report.hero:
        recs.append(("hero", report.hero))
    for i, opp in enumerate(report.content_opportunities or []):
        recs.append((f"content_{i + 1}", opp))
    for i, opp in enumerate(report.ad_opportunities or []):
        recs.append((f"ad_{i + 1}", opp))
    if report.trend:
        recs.append(("trend", report.trend))
    return recs


async def seed_study_abroad(session, tenant) -> dict:
    """Bootstrap profile + historical data. Returns summary counts."""
    from aicmo.modules.advisor.connectors import upsert_metric
    from aicmo.modules.advisor.models import AdvisorOutcome, AdvisorRecommendation
    from aicmo.modules.integrations.models import IntegrationConnection
    from aicmo.modules.leads import service as leads_service
    from aicmo.modules.leads.schemas import LeadImportPayload
    from aicmo.modules.onboarding import service as onboarding_service
    from aicmo.modules.onboarding.schemas import BusinessProfileCreate
    from aicmo.modules.performance import service as performance_service
    from aicmo.modules.social import service as social_service
    from aicmo.modules.social.analyzer import run_analyzer
    from aicmo.modules.social.models import WinningPattern
    from aicmo.modules.social.schemas import ManualImportPayload

    profile_payload = BusinessProfileCreate(
        business_name="GlobalPath Study Abroad",
        website="https://globalpath.example.com",
        industry="Study Abroad Consultancy",
        business_type="Education consultancy",
        target_audience=(
            "Students aged 18–28 and their parents in Hyderabad and Telangana "
            "planning UK, Canada, or Australia admissions — typically 6.0–7.0 IELTS, "
            "budget-conscious, researching visa timelines and total cost of study."
        ),
        brand_tone="Trustworthy and expert",
        competitors=["IDP Education", "Edwise", "Leap Scholar"],
        goals=[
            "Increase qualified counselling bookings",
            "Grow Instagram leads for UK September intake",
        ],
        preferred_platforms=["Instagram", "Google Business Profile", "WhatsApp"],
        business_location="Hyderabad, Telangana, India",
        current_monthly_leads_band="20-50",
        monthly_budget_band="₹50,000–₹1,50,000",
        primary_goal_text=(
            "Book 40 qualified UK/Canada counselling sessions per month from "
            "Instagram and local Google searches."
        ),
    )
    profile, _ = await onboarding_service.create_or_replace_profile(
        session, tenant=tenant, payload=profile_payload
    )

    ig_raw = json.loads((FIXTURES / "instagram_posts.json").read_text())
    ig_payload = ManualImportPayload.model_validate(ig_raw)
    ig_result = await social_service.manual_import(
        session, tenant=tenant, payload=ig_payload
    )

    leads_csv = (FIXTURES / "leads.csv").read_text()
    lead_result = await leads_service.import_csv(
        session,
        tenant=tenant,
        csv_text=LeadImportPayload(csv=leads_csv).csv,
    )

    campaign_csv = (FIXTURES / "campaign_performance.csv").read_text()
    perf_result = await performance_service.ingest_csv(
        session,
        tenant=tenant,
        payload=campaign_csv,
        filename="study_abroad_campaigns.csv",
    )

    now = datetime.now(UTC)
    gbp_conn = IntegrationConnection(
        id=uuid.uuid4(),
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        provider_slug="google_business_profile",
        external_account_id="globalpath-gachibowli",
        external_account_name="GlobalPath Study Abroad — Gachibowli",
        state="ACTIVE",
        scopes_granted=["business.manage"],
        connected_at=now - timedelta(days=90),
        last_sync_at=now,
        created_by_user_id=tenant.user_uuid,
    )
    session.add(gbp_conn)
    await session.flush()

    gbp_metrics = {
        "profile_views": 1842.0,
        "call_clicks": 67.0,
        "website_clicks": 124.0,
        "direction_requests": 89.0,
        "reviews_count": 47.0,
        "reviews_average_rating": 4.7,
    }
    for key, value in gbp_metrics.items():
        await upsert_metric(
            session,
            brand_id=tenant.brand_id,
            provider_slug="google_business_profile",
            metric_key=key,
            metric_value=value,
            period_end=now,
            raw_json={"source": "historical_import", "location": "Gachibowli"},
        )

    session.add(
        WinningPattern(
            id=uuid.uuid4(),
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
            platform="instagram",
            hook_pattern="Deadline urgency + document checklist",
            visual_pattern="Carousel with numbered slides",
            caption_pattern="Country-specific intake deadline in first line",
            cta_pattern="Save for later + DM for checklist",
            format_pattern="carousel",
            posting_time_pattern="Tue/Thu 11:00–12:00 IST",
            summary=(
                "UK intake deadline carousels outperform single-image posts "
                "by 2.3× saves and drive counselling DMs."
            ),
            performance_score=0.82,
            source_asset_ids=["gp_uk_intake_jan2025"],
        )
    )

    past_rec_id = uuid.uuid4()
    session.add(
        AdvisorRecommendation(
            id=past_rec_id,
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
            record_type="recommendation_created",
            title="UK intake deadline carousel",
            description="Publish a UK September intake checklist carousel",
            status="completed",
            impact_score=78,
            confidence=78,
            impact_category="lead",
            observation=(
                "Instagram saves on UK checklist carousel were 156 vs 42 on parent FAQ post."
            ),
            root_cause=(
                "Deadline-driven carousels match Hyderabad students researching CAS timelines."
            ),
            why="Deadline-driven carousels match Hyderabad students researching CAS timelines.",
            expected_result="Increase qualified UK counselling DMs within 7 days.",
            data_used=[{"key": "instagram_organic:reach_28d", "label": "Reach", "value": "6,100"}],
            source_surface="intelligence_content",
            source_fingerprint="validation:uk-carousel-success",
            completed_at=now - timedelta(days=30),
        )
    )

    skipped_rec_id = uuid.uuid4()
    session.add(
        AdvisorRecommendation(
            id=skipped_rec_id,
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
            record_type="recommendation_created",
            title="Generic motivational quote post",
            description="Post an inspirational study-abroad quote",
            status="skipped",
            impact_score=20,
            confidence=25,
            impact_category="lead",
            observation="Low engagement on generic quote posts historically.",
            root_cause="No specific country, deadline, or document hook.",
            why="No specific country, deadline, or document hook.",
            expected_result="Minimal lead impact expected.",
            data_used=[],
            source_surface="intelligence_content",
            source_fingerprint="validation:generic-quote-skipped",
            skipped_at=now - timedelta(days=10),
        )
    )
    await session.flush()

    session.add(
        AdvisorOutcome(
            id=uuid.uuid4(),
            brand_id=tenant.brand_id,
            recommendation_id=past_rec_id,
            evaluation_status="evaluated",
            baseline_snapshot={"leads_in_window": 4},
            outcome_snapshot={"leads_in_window": 12},
            delta_summary=(
                "Leads in the 14-day window: 12 vs 4 at completion (+8). "
                "Published carousel reach 6,100."
            ),
            effectiveness_score=82,
            evaluate_after=now - timedelta(days=16),
            evaluated_at=now - timedelta(days=16),
        )
    )
    session.add(
        AdvisorOutcome(
            id=uuid.uuid4(),
            brand_id=tenant.brand_id,
            recommendation_id=skipped_rec_id,
            evaluation_status="evaluated",
            baseline_snapshot={},
            outcome_snapshot={"skipped": True},
            delta_summary="Skipped — do not recommend similar actions.",
            effectiveness_score=0,
            evaluate_after=now - timedelta(days=10),
            evaluated_at=now - timedelta(days=10),
        )
    )
    await session.flush()
    await session.commit()

    analyze_result = await run_analyzer(session, tenant=tenant, platform="instagram")

    return {
        "profile_id": str(profile.id),
        "instagram_assets": ig_result.inserted_assets + ig_result.updated_assets,
        "instagram_signals": ig_result.inserted_signals,
        "leads_inserted": lead_result.inserted,
        "campaign_rows": perf_result.rows_accepted,
        "gbp_metrics": len(gbp_metrics),
        "patterns_from_analyzer": analyze_result.patterns_created,
    }


async def run_intelligence(session, tenant, profile) -> tuple:
    from aicmo.modules.advisor.intelligence import compose_intelligence
    from aicmo.modules.advisor.signals import gather_intelligence_signals

    ctx = await gather_intelligence_signals(
        session, profile=profile, brand_id=tenant.brand_id
    )
    report = await compose_intelligence(session, profile=profile, tenant=tenant)
    return ctx, report


async def generate_assets(session, tenant, report) -> list[dict]:
    """Generate poster, carousel, reel, and ad from recommendation context."""
    from aicmo.modules.ads import service as ads_service
    from aicmo.modules.ads.schemas import GenerateAdRequest
    from aicmo.modules.content import service as content_service
    from aicmo.modules.content.schemas import GenerateRequest
    from aicmo.modules.visuals import service as visuals_service
    from aicmo.modules.visuals.schemas import GenerateVisualRequest

    results: list[dict] = []
    # Keep goals under 96 chars — generated_visuals.business_goal is VARCHAR(96).
    poster_goal = "UK September intake counselling poster for GlobalPath"
    carousel_goal = "UK CAS document checklist carousel for Hyderabad students"
    reel_goal = "Canada PNP vs Express Entry explainer reel"
    landing_goal = "Free UK counselling landing page for Hyderabad students"
    ad_goal = "Book free UK/Canada counselling session"

    asset_specs = [
        (
            "poster",
            lambda: visuals_service.generate(
                session,
                tenant=tenant,
                payload=GenerateVisualRequest(
                    visual_type="ad_creative",
                    platform="Instagram",
                    goal=poster_goal,
                ),
            ),
        ),
        (
            "carousel",
            lambda: content_service.generate(
                session,
                tenant=tenant,
                payload=GenerateRequest(
                    content_type="carousel",
                    platform="Instagram",
                    goal=carousel_goal,
                ),
            ),
        ),
        (
            "reel",
            lambda: content_service.generate(
                session,
                tenant=tenant,
                payload=GenerateRequest(
                    content_type="reel",
                    platform="Instagram",
                    goal=reel_goal,
                ),
            ),
        ),
        (
            "ad_creative",
            lambda: ads_service.generate(
                session,
                tenant=tenant,
                payload=GenerateAdRequest(
                    ad_type="instagram_promo",
                    objective="leads",
                    goal=ad_goal,
                ),
            ),
        ),
        (
            "landing_page_copy",
            lambda: content_service.generate(
                session,
                tenant=tenant,
                payload=GenerateRequest(
                    content_type="landing_page_copy",
                    platform="Website",
                    goal=landing_goal,
                ),
            ),
        ),
    ]

    for name, factory in asset_specs:
        try:
            result = await factory()
            await session.commit()
            results.append(
                {
                    "asset": name,
                    "status": "created",
                    "id": str(getattr(result, "id", "")),
                }
            )
        except Exception as exc:  # noqa: BLE001 — validation report must continue
            await session.rollback()
            results.append({"asset": name, "status": "failed", "error": str(exc)[:200]})
    return results


async def main(skip_assets: bool = False) -> int:
    _load_env()
    from aicmo.config import get_settings
    from aicmo.db.session import SessionLocal
    from aicmo.modules.onboarding import service as onboarding_service
    from aicmo.modules.orgs import service as orgs_service
    from aicmo.modules.orgs.schemas import OrganizationCreate
    from aicmo.modules.users.service import get_or_create_from_clerk
    from aicmo.tenancy.context import TenantContext

    settings = get_settings()
    _print_section("Study Abroad Intelligence Validation — GlobalPath")
    print(f"Database: {settings.database_url.split('@')[-1]}")
    print(f"Intelligence enabled: {settings.advisor_intelligence_enabled}")

    async with SessionLocal() as session:
        run_id = uuid.uuid4().hex[:10]
        user = await get_or_create_from_clerk(
            session,
            clerk_user_id=f"validation_study_abroad_{run_id}",
            email=f"validation+{run_id}@globalpath.example.com",
            display_name="Validation Runner",
        )
        org_result = await orgs_service.create_organization(
            session,
            actor_user=user,
            payload=OrganizationCreate(
                name=f"GlobalPath Validation {uuid.uuid4().hex[:6]}",
                brand_name="GlobalPath Study Abroad",
            ),
        )
        await session.commit()

        tenant = TenantContext(
            user_id=user.clerk_user_id,
            user_uuid=user.id,
            organization_id=org_result.organization.id,
            brand_id=org_result.brand_id,
            member_id=org_result.member_id,
        )

        _print_section("1. Onboarding + historical data import")
        seed_summary = await seed_study_abroad(session, tenant)
        for key, val in seed_summary.items():
            print(f"  {key}: {val}")

        profile_row = await onboarding_service.require_profile(session, tenant.brand_id)
        from aicmo.modules.onboarding.schemas import BusinessProfileResponse

        profile = BusinessProfileResponse.model_validate(profile_row)

        _print_section("2. Intelligence engine compose")
        ctx, report = await run_intelligence(session, tenant, profile)

        signal_errors = validate_signal_coverage(ctx, report)
        if signal_errors:
            print("Signal layer gaps:")
            for err in signal_errors:
                print(f"  ✗ {err}")
        else:
            print("Signal layers loaded:")
            print(f"  ✓ Business Brain — {ctx.brain.business_name}, {ctx.brain.industry}")
            print(f"  ✓ Historical Outcomes — {len(ctx.outcome_context.get('recent_outcomes', []))} evaluated")
            ig_metrics = [m for m in ctx.connector_context.get('metrics', []) if 'instagram' in m.get('provider', '')]
            gbp_metrics = [m for m in ctx.connector_context.get('metrics', []) if m.get('provider') == 'google_business_profile']
            print(f"  ✓ Instagram Metrics — {len(ig_metrics)} metrics")
            print(f"  ✓ Google Business Metrics — {len(gbp_metrics)} metrics")
            print(f"  ✓ Lead activity — {ctx.activity_signals} signals, hot={ctx.lead_context.get('counts', {}).get('hot', 'n/a')}")

        if not report.ready:
            print("\nIntelligence NOT READY:")
            empty = report.empty
            if empty:
                print(f"  Headline: {empty.headline}")
                print(f"  Message: {empty.message}")
                if empty.suggested_setup_steps:
                    print("  Setup steps:", ", ".join(empty.suggested_setup_steps))
            return 1

        print(f"\nReport ready — confidence cap: {report.confidence_cap}")
        if report.daily_brief:
            print(f"\nDaily brief: {report.daily_brief.what_happened[:200]}...")

        all_errors: list[str] = []
        recs = collect_recommendations(report)
        _print_section("3. Recommendation contract validation")
        for label, rec in recs:
            errors = validate_recommendation_contract(rec, label=label)
            all_errors.extend(errors)
            status = "✗ FAIL" if errors else "✓ PASS"
            print(f"\n  [{status}] {label}")
            print(f"    Observation: {rec.observation[:120]}...")
            print(f"    Action: {rec.recommended_action[:120]}...")
            print(f"    Confidence: {rec.confidence}")
            src_keys = [s.key for s in (rec.data_sources_used or [])[:4]]
            print(f"    Data sources: {', '.join(src_keys)}")

        asset_results: list[dict] = []
        if not skip_assets:
            _print_section("4. Production asset generation")
            asset_results = await generate_assets(session, tenant, report)
            for row in asset_results:
                if row["status"] == "created":
                    print(f"  ✓ {row['asset']}: id={row['id']}")
                else:
                    print(f"  ✗ {row['asset']}: {row.get('error', 'unknown')}")

        _print_section("Validation summary")
        print(f"  Brand ID: {tenant.brand_id}")
        print(f"  Recommendations checked: {len(recs)}")
        print(f"  Contract errors: {len(all_errors)}")
        print(f"  Signal layer errors: {len(signal_errors)}")
        if not skip_assets:
            created = sum(1 for r in asset_results if r["status"] == "created")
            print(f"  Assets generated: {created}/{len(asset_results)}")

        if all_errors:
            print("\nContract failures:")
            for err in all_errors[:10]:
                print(f"  - {err}")

        if signal_errors or all_errors:
            return 1
        print("\n✓ Validation PASSED — intelligence engine grounded on real business data.")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-assets",
        action="store_true",
        help="Skip LLM asset generation (intelligence validation only)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(skip_assets=args.skip_assets)))
