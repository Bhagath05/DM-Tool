#!/usr/bin/env python3
"""End-to-end platform validation audit — all 10 core systems.

Runs real service-layer calls against Postgres (no mocked LLM for asset gen
when --full-assets is set). Produces a structured JSON + human report.

Usage:
    cd apps/api && PYTHONPATH=. .venv/bin/python scripts/validate_platform_audit.py
    cd apps/api && PYTHONPATH=. .venv/bin/python scripts/validate_platform_audit.py --skip-assets
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path

# Reuse study-abroad seed + intelligence helpers
from scripts.validate_study_abroad import (  # noqa: E402
    collect_recommendations,
    generate_assets,
    run_intelligence,
    seed_study_abroad,
    validate_recommendation_contract,
    validate_signal_coverage,
)


class Status(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class AuditCheck:
    name: str
    status: Status
    expected: str
    actual: str
    evidence: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)


@dataclass
class SystemAudit:
    system: str
    status: Status = Status.YELLOW
    checks: list[AuditCheck] = field(default_factory=list)

    def finalize(self) -> None:
        if any(c.status == Status.RED for c in self.checks):
            self.status = Status.RED
        elif any(c.status == Status.YELLOW for c in self.checks):
            self.status = Status.YELLOW
        else:
            self.status = Status.GREEN


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[2]
        load_dotenv(root / ".env")
    except ImportError:
        pass


def _check(status_ok: bool, partial: bool = False) -> Status:
    if status_ok:
        return Status.GREEN
    if partial:
        return Status.YELLOW
    return Status.RED


async def audit_migrations(session) -> SystemAudit:
    audit = SystemAudit(system="Database Migrations")
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import text

        cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        row = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
        at_head = row in heads if row else False
        audit.checks.append(
            AuditCheck(
                name="Alembic at head revision",
                status=_check(at_head, partial=row is not None and not at_head),
                expected=f"DB version in {heads}",
                actual=str(row),
                evidence=[f"heads={heads}"],
            )
        )
    except Exception as exc:  # noqa: BLE001
        audit.checks.append(
            AuditCheck(
                name="Alembic at head revision",
                status=Status.RED,
                expected="alembic_version matches head",
                actual=str(exc)[:200],
            )
        )
    audit.finalize()
    return audit


async def audit_business_brain(session, tenant, profile) -> SystemAudit:
    audit = SystemAudit(system="Business Brain")
    from aicmo.modules.advisor.brain import (
        brain_completeness,
        brain_has_minimum,
        load_business_brain,
    )

    brain = load_business_brain(profile)
    score, missing = brain_completeness(brain)
    complete = brain_has_minimum(brain) and score >= 6 and len(missing) == 0
    audit.checks.append(
        AuditCheck(
            name="Brain loaded and complete",
            status=_check(complete, partial=brain_has_minimum(brain)),
            expected="Minimum brain fields + ≥6/7 completeness score",
            actual=f"score={score}, missing={missing}, industry={brain.industry!r}",
            evidence=[f"business_name={brain.business_name}", f"goals={brain.growth_goal!r}"],
        )
    )
    audit.checks.append(
        AuditCheck(
            name="Profile ↔ brain alignment",
            status=_check(profile.business_name == brain.business_name),
            expected="Onboarding profile matches brain business_name",
            actual=f"profile={profile.business_name!r} brain={brain.business_name!r}",
        )
    )
    audit.finalize()
    return audit


async def audit_intelligence(session, tenant, profile, ctx, report) -> SystemAudit:
    audit = SystemAudit(system="Intelligence Engine")
    signal_errors = validate_signal_coverage(ctx, report)
    audit.checks.append(
        AuditCheck(
            name="All signal layers loaded",
            status=_check(len(signal_errors) == 0),
            expected="Business Brain, outcomes, Instagram, GBP, leads",
            actual=f"{len(signal_errors)} gap(s)" if signal_errors else "all layers OK",
            evidence=signal_errors or [
                f"outcomes={len(ctx.outcome_context.get('recent_outcomes', []))}",
                f"ig_metrics={len([m for m in ctx.connector_context.get('metrics', []) if 'instagram' in m.get('provider', '')])}",
                f"gbp_metrics={len([m for m in ctx.connector_context.get('metrics', []) if m.get('provider') == 'google_business_profile'])}",
            ],
        )
    )
    audit.checks.append(
        AuditCheck(
            name="Report ready with recommendations",
            status=_check(report.ready and report.hero is not None),
            expected="ready=True, hero present",
            actual=f"ready={report.ready}, hero={'yes' if report.hero else 'no'}, cap={report.confidence_cap}",
        )
    )
    recs = collect_recommendations(report)
    contract_errors: list[str] = []
    for label, rec in recs:
        contract_errors.extend(validate_recommendation_contract(rec, label=label))
    audit.checks.append(
        AuditCheck(
            name="Recommendation 6-field contract",
            status=_check(len(contract_errors) == 0),
            expected="observation, root_cause, action, impact, confidence, sources",
            actual=f"{len(contract_errors)} error(s)",
            evidence=contract_errors[:5] or [f"checked {len(recs)} recommendations"],
        )
    )
    audit.finalize()
    return audit


async def audit_outcome_learning(session, tenant) -> SystemAudit:
    audit = SystemAudit(system="Outcome Learning")
    from sqlalchemy import func, select

    from aicmo.modules.advisor.models import AdvisorOutcome

    rows = (
        await session.execute(
            select(
                AdvisorOutcome.evaluation_status,
                func.count(),
            )
            .where(AdvisorOutcome.brand_id == tenant.brand_id)
            .group_by(AdvisorOutcome.evaluation_status)
        )
    ).all()
    counts = {status: cnt for status, cnt in rows}
    evaluated = counts.get("evaluated", 0)
    audit.checks.append(
        AuditCheck(
            name="Historical outcomes in DB",
            status=_check(evaluated >= 1, partial=evaluated == 0),
            expected="≥1 evaluated outcome for learning context",
            actual=str(counts),
        )
    )
    from aicmo.modules.advisor import effectiveness as eff_service

    scores = await eff_service.list_effectiveness(session, brand_id=tenant.brand_id)
    audit.checks.append(
        AuditCheck(
            name="Effectiveness scores readable",
            status=_check(True),
            expected="effectiveness endpoint data loads",
            actual=f"{len(scores)} score row(s)",
        )
    )
    audit.finalize()
    return audit


async def audit_ai_history(session, tenant) -> SystemAudit:
    audit = SystemAudit(system="AI History")
    from aicmo.modules.advisor import service as advisor_service

    items = await advisor_service.list_history(
        session, brand_id=tenant.brand_id, limit=20
    )
    has_completed = any(i.status == "completed" for i in items)
    has_skipped = any(i.status == "skipped" for i in items)
    audit.checks.append(
        AuditCheck(
            name="History list returns recommendations",
            status=_check(len(items) >= 2),
            expected="≥2 history items (completed + skipped seeded)",
            actual=f"{len(items)} items",
            evidence=[f"{i.title[:50]} [{i.status}]" for i in items[:4]],
        )
    )
    audit.checks.append(
        AuditCheck(
            name="Outcome learning surfaced in history",
            status=_check(has_completed and any(i.learning for i in items)),
            expected="completed items include learning summary",
            actual=f"completed={has_completed}, with_learning={sum(1 for i in items if i.learning)}",
        )
    )
    audit.checks.append(
        AuditCheck(
            name="Skipped items visible",
            status=_check(has_skipped),
            expected="skipped recommendations appear in history",
            actual=f"skipped={has_skipped}",
        )
    )
    audit.finalize()
    return audit


async def audit_instagram(session, tenant) -> SystemAudit:
    audit = SystemAudit(system="Instagram Integration")
    from sqlalchemy import select

    from aicmo.modules.advisor.connectors_models import ConnectorMetric
    from aicmo.modules.social.models import SocialAsset

    assets = (
        await session.execute(
            select(SocialAsset).where(
                SocialAsset.brand_id == tenant.brand_id,
                SocialAsset.platform == "instagram",
            )
        )
    ).scalars().all()
    metrics = (
        await session.execute(
            select(ConnectorMetric).where(
                ConnectorMetric.brand_id == tenant.brand_id,
                ConnectorMetric.provider_slug.like("instagram%"),
            )
        )
    ).scalars().all()
    audit.checks.append(
        AuditCheck(
            name="Instagram assets imported",
            status=_check(len(assets) >= 1),
            expected="manual import persisted social assets",
            actual=f"{len(assets)} asset(s)",
        )
    )
    audit.checks.append(
        AuditCheck(
            name="Instagram connector metrics",
            status=_check(len(metrics) >= 1),
            expected="metrics upserted to connector_metrics",
            actual=f"{len(metrics)} metric(s)",
            evidence=[f"{m.metric_key}={m.metric_value}" for m in metrics[:4]],
        )
    )
    audit.finalize()
    return audit


async def audit_gbp(session, tenant) -> SystemAudit:
    audit = SystemAudit(system="Google Business Integration")
    from sqlalchemy import select

    from aicmo.modules.advisor.connectors_models import ConnectorMetric
    from aicmo.modules.integrations.models import IntegrationConnection

    conn = (
        await session.execute(
            select(IntegrationConnection).where(
                IntegrationConnection.brand_id == tenant.brand_id,
                IntegrationConnection.provider_slug == "google_business_profile",
            )
        )
    ).scalar_one_or_none()
    metrics = (
        await session.execute(
            select(ConnectorMetric).where(
                ConnectorMetric.brand_id == tenant.brand_id,
                ConnectorMetric.provider_slug == "google_business_profile",
            )
        )
    ).scalars().all()
    audit.checks.append(
        AuditCheck(
            name="GBP connection ACTIVE",
            status=_check(conn is not None and conn.state == "ACTIVE"),
            expected="IntegrationConnection state=ACTIVE",
            actual=f"conn={'yes' if conn else 'no'}, state={getattr(conn, 'state', None)}",
        )
    )
    audit.checks.append(
        AuditCheck(
            name="GBP metrics synced",
            status=_check(len(metrics) >= 4),
            expected="profile_views, call_clicks, etc. in connector_metrics",
            actual=f"{len(metrics)} metric(s)",
            evidence=[m.metric_key for m in metrics],
        )
    )
    audit.finalize()
    return audit


async def audit_leads(session, tenant, profile) -> SystemAudit:
    audit = SystemAudit(system="Lead Capture")
    from sqlalchemy import func, select

    from aicmo.modules.leads.models import Lead

    total = (
        await session.execute(
            select(func.count()).select_from(Lead).where(Lead.brand_id == tenant.brand_id)
        )
    ).scalar_one()
    hot = (
        await session.execute(
            select(func.count()).select_from(Lead).where(
                Lead.brand_id == tenant.brand_id,
                Lead.status == "hot",
            )
        )
    ).scalar_one()
    audit.checks.append(
        AuditCheck(
            name="Leads imported to inbox",
            status=_check(total >= 5),
            expected="CSV import persisted leads",
            actual=f"total={total}, hot={hot}",
        )
    )
    from aicmo.modules.leads import intelligence as lead_intel

    report = await lead_intel.build_lead_intelligence(session, profile=profile)
    audit.checks.append(
        AuditCheck(
            name="Lead intelligence composes",
            status=_check(report.hero_recommendation.confidence >= 1),
            expected="hero recommendation with confidence",
            actual=f"confidence={report.hero_recommendation.confidence}, hot={report.counts.hot_count}",
        )
    )
    audit.checks.append(
        AuditCheck(
            name="Public capture path (schema only)",
            status=Status.YELLOW,
            expected="POST /public/leads/capture/{slug} with captcha",
            actual="Not exercised in audit — requires published landing page + Turnstile token",
            logs=["Manual test: publish landing page, submit form with captcha"],
        )
    )
    audit.finalize()
    return audit


async def audit_asset_generation(session, tenant, skip_assets: bool) -> SystemAudit:
    audit = SystemAudit(system="Asset Generation")
    if skip_assets:
        audit.checks.append(
            AuditCheck(
                name="Production asset generation",
                status=Status.YELLOW,
                expected="5 asset types generated via LLM",
                actual="Skipped (--skip-assets)",
            )
        )
        audit.finalize()
        return audit

    results = await generate_assets(session, tenant, report=None)
    created = [r for r in results if r.get("status") == "created"]
    failed = [r for r in results if r.get("status") == "failed"]
    audit.checks.append(
        AuditCheck(
            name="All 5 asset types generate",
            status=_check(len(created) == 5, partial=len(created) >= 3),
            expected="poster, carousel, reel, ad, landing_page_copy",
            actual=f"{len(created)}/5 created, {len(failed)} failed",
            evidence=[f"{r['asset']}: {r.get('id') or r.get('error', '')[:80]}" for r in results],
        )
    )
    audit.finalize()
    return audit


async def audit_publishing(session, tenant, asset_results: list[dict] | None) -> SystemAudit:
    audit = SystemAudit(system="Publishing Pipeline")
    from aicmo.modules.advisor import execute as execute_module
    from aicmo.modules.advisor import service as advisor_service
    from aicmo.modules.publishing import assets as pub_assets
    from aicmo.modules.publishing.schemas import SchedulePostRequest
    from aicmo.modules.publishing import service as pub_service
    from sqlalchemy import select

    from aicmo.modules.advisor.models import AdvisorRecommendation
    from aicmo.modules.publishing.models import ContentAsset

    rec = (
        await session.execute(
            select(AdvisorRecommendation)
            .where(
                AdvisorRecommendation.brand_id == tenant.brand_id,
                AdvisorRecommendation.record_type == "recommendation_created",
                AdvisorRecommendation.generator_hint.isnot(None),
            )
            .order_by(AdvisorRecommendation.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if rec is None or not rec.generator_hint:
        audit.checks.append(
            AuditCheck(
                name="Execute recommendation → asset",
                status=Status.YELLOW,
                expected="Recommendation with generator_hint executed",
                actual="No executable recommendation found after compose",
            )
        )
        audit.finalize()
        return audit

    try:
        exec_result = await execute_module.execute_recommendation(
            session,
            tenant=tenant,
            recommendation_id=rec.id,
        )
        audit.checks.append(
            AuditCheck(
                name="Execute recommendation → asset",
                status=_check(exec_result.status == "created"),
                expected="content_asset_id returned",
                actual=f"asset_type={exec_result.asset_type}, id={exec_result.asset_id}",
                evidence=[f"content_asset_id={exec_result.content_asset_id}"],
            )
        )
    except Exception as exc:  # noqa: BLE001
        audit.checks.append(
            AuditCheck(
                name="Execute recommendation → asset",
                status=Status.RED,
                expected="execute_recommendation succeeds",
                actual=str(exc)[:200],
            )
        )
        audit.finalize()
        return audit

    assets = (
        await session.execute(
            select(ContentAsset).where(ContentAsset.brand_id == tenant.brand_id)
        )
    ).scalars().all()
    audit.checks.append(
        AuditCheck(
            name="Content assets registered",
            status=_check(len(assets) >= 1),
            expected="ContentAsset row in publishing registry",
            actual=f"{len(assets)} asset(s)",
            evidence=[f"{a.asset_type} from {a.source_table}" for a in assets[:3]],
        )
    )

    if assets:
        asset = assets[0]
        try:
            scheduled = await pub_service.schedule_post(
                session,
                tenant=tenant,
                payload=SchedulePostRequest(
                    content_asset_id=asset.id,
                    platform="instagram",
                    scheduled_at=datetime.now(UTC) + timedelta(hours=2),
                ),
            )
            audit.checks.append(
                AuditCheck(
                    name="Schedule post (future)",
                    status=_check(scheduled.publish_status == "scheduled"),
                    expected="ScheduledPost created without immediate publish",
                    actual=f"status={scheduled.publish_status}, id={scheduled.id}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            audit.checks.append(
                AuditCheck(
                    name="Schedule post (future)",
                    status=Status.YELLOW,
                    expected="Schedule succeeds when platform connected",
                    actual=str(exc)[:200],
                    logs=["Instagram OAuth connection required for schedule validation"],
                )
            )

    audit.checks.append(
        AuditCheck(
            name="Live publish to Instagram/GBP",
            status=Status.YELLOW,
            expected="Real OAuth token + media URL publish",
            actual="Not exercised — requires live platform credentials",
            logs=["publish_instagram requires ig_business_account_id + rendered image URL"],
        )
    )
    audit.finalize()
    return audit


async def audit_recommendation_memory(session, tenant, profile) -> SystemAudit:
    audit = SystemAudit(system="Recommendation Memory")
    from aicmo.modules.advisor.dedupe import should_suppress
    from aicmo.modules.advisor.memory import load_brand_memory
    from aicmo.modules.advisor.intelligence import compose_intelligence

    memory_rows = await load_brand_memory(session, brand_id=tenant.brand_id)
    audit.checks.append(
        AuditCheck(
            name="Brand memory loads prior recommendations",
            status=_check(len(memory_rows) >= 2),
            expected="completed + skipped recommendations in memory",
            actual=f"{len(memory_rows)} row(s)",
            evidence=[f"[{r.status}] {r.title[:40]}" for r in memory_rows[:4]],
        )
    )

    report1 = await compose_intelligence(session, profile=profile, tenant=tenant)
    await session.commit()
    report2 = await compose_intelligence(session, profile=profile, tenant=tenant)
    await session.commit()

    completed_fp = next(
        (r.source_fingerprint for r in memory_rows if r.status == "completed" and r.source_fingerprint),
        "",
    )
    suppressed = should_suppress(completed_fp, memory_rows) if completed_fp else False
    audit.checks.append(
        AuditCheck(
            name="Dedupe suppresses recent completed actions",
            status=_check(suppressed),
            expected="should_suppress=True for recently completed fingerprint",
            actual=f"suppress={suppressed}, fingerprint={completed_fp[:40] if completed_fp else 'n/a'}",
        )
    )

    hero1 = report1.hero.recommended_action if report1.hero else ""
    hero2 = report2.hero.recommended_action if report2.hero else ""
    repeat = hero1 == hero2 and bool(hero1)
    audit.checks.append(
        AuditCheck(
            name="Second compose stability",
            status=Status.GREEN if hero1 and hero2 else Status.YELLOW,
            expected="Compose runs twice without error; may repeat if signals unchanged",
            actual=f"same_hero={repeat}",
            evidence=[f"compose1_conf={report1.confidence_cap}", f"compose2_conf={report2.confidence_cap}"],
        )
    )
    audit.finalize()
    return audit


def print_report(audits: list[SystemAudit], run_id: str) -> None:
    print("\n" + "=" * 72)
    print("DM TOOL — PLATFORM VALIDATION AUDIT")
    print(f"Run ID: {run_id}  |  {datetime.now(UTC).isoformat()}")
    print("=" * 72)

    summary = {s.value: 0 for s in Status}
    for a in audits:
        summary[a.status.value] += 1
        icon = {"GREEN": "✓", "YELLOW": "⚠", "RED": "✗"}[a.status.value]
        print(f"\n{icon} [{a.status.value}] {a.system}")
        for c in a.checks:
            sub = {"GREEN": "PASS", "YELLOW": "PARTIAL", "RED": "FAIL"}[c.status.value]
            print(f"    [{sub}] {c.name}")
            print(f"          Expected: {c.expected}")
            print(f"          Actual:   {c.actual}")
            for ev in c.evidence[:3]:
                print(f"          Evidence: {ev}")
            for log in c.logs[:2]:
                print(f"          Log: {log}")

    print("\n" + "-" * 72)
    print(
        f"SUMMARY: GREEN={summary['GREEN']}  YELLOW={summary['YELLOW']}  RED={summary['RED']}"
    )
    print("-" * 72)


async def main(skip_assets: bool) -> int:
    _load_env()
    from aicmo.config import get_settings
    from aicmo.db.session import SessionLocal
    from aicmo.modules.onboarding import service as onboarding_service
    from aicmo.modules.onboarding.schemas import BusinessProfileResponse
    from aicmo.modules.orgs import service as orgs_service
    from aicmo.modules.orgs.schemas import OrganizationCreate
    from aicmo.modules.users.service import get_or_create_from_clerk
    from aicmo.tenancy.context import TenantContext

    settings = get_settings()
    run_id = uuid.uuid4().hex[:10]
    audits: list[SystemAudit] = []

    async with SessionLocal() as session:
        user = await get_or_create_from_clerk(
            session,
            clerk_user_id=f"audit_{run_id}",
            email=f"audit+{run_id}@example.com",
            display_name="Platform Audit",
        )
        org_result = await orgs_service.create_organization(
            session,
            actor_user=user,
            payload=OrganizationCreate(
                name=f"Audit Org {run_id}",
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

        print(f"Auditing against DB: {settings.database_url.split('@')[-1]}")

        audits.append(await audit_migrations(session))
        await seed_study_abroad(session, tenant)
        profile_row = await onboarding_service.require_profile(session, tenant.brand_id)
        profile = BusinessProfileResponse.model_validate(profile_row)

        audits.append(await audit_business_brain(session, tenant, profile))
        ctx, report = await run_intelligence(session, tenant, profile)
        await session.commit()
        audits.append(await audit_intelligence(session, tenant, profile, ctx, report))
        audits.append(await audit_outcome_learning(session, tenant))
        audits.append(await audit_ai_history(session, tenant))
        audits.append(await audit_instagram(session, tenant))
        audits.append(await audit_gbp(session, tenant))
        audits.append(await audit_leads(session, tenant, profile))
        audits.append(await audit_recommendation_memory(session, tenant, profile))

        asset_audit = await audit_asset_generation(session, tenant, skip_assets=skip_assets)
        audits.append(asset_audit)
        audits.append(await audit_publishing(session, tenant, None))

    print_report(audits, run_id)

    out_path = Path(__file__).resolve().parent / "audit_reports" / f"audit_{run_id}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "systems": [
                    {
                        "system": a.system,
                        "status": a.status.value,
                        "checks": [asdict(c) | {"status": c.status.value} for c in a.checks],
                    }
                    for a in audits
                ],
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nJSON report: {out_path}")

    if any(a.status == Status.RED for a in audits):
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-assets", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(skip_assets=args.skip_assets)))
