#!/usr/bin/env python3
"""End-to-end verification of all 6 publishing platform integrations.

Checks OAuth config, provider availability, DB state, encryption,
publishing paths, and scheduler wiring. Does NOT mock — reads real env + DB.

Usage:
    cd apps/api && PYTHONPATH=. .venv/bin/python scripts/verify_platform_integrations.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

root = Path(__file__).resolve().parents[2]
load_dotenv(root / ".env")


class Severity(str, Enum):
    BLOCKER = "BLOCKER"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


@dataclass
class PlatformReport:
    platform: str
    oauth_status: str
    connection_status: str
    publishing_status: str
    scheduler_status: str
    issues: list[str] = field(default_factory=list)
    severity: Severity = Severity.NONE
    evidence: list[str] = field(default_factory=list)


PLATFORMS = {
    "instagram": {
        "stack": "social",
        "client_id_env": "IG_CLIENT_ID",
        "client_secret_env": "IG_CLIENT_SECRET",
        "redirect": "/api/v1/social/oauth/instagram/callback",
        "publish_key": "instagram",
        "provider_slug": None,
    },
    "facebook": {
        "stack": "integrations",
        "client_id_env": "FB_CLIENT_ID",
        "client_secret_env": "FB_CLIENT_SECRET",
        "fallback_id": "IG_CLIENT_ID",
        "fallback_secret": "IG_CLIENT_SECRET",
        "redirect": "/api/v1/integrations/oauth/callback",
        "publish_key": "facebook",
        "provider_slug": "facebook_pages",
    },
    "linkedin": {
        "stack": "integrations",
        "client_id_env": "LINKEDIN_CLIENT_ID",
        "client_secret_env": "LINKEDIN_CLIENT_SECRET",
        "redirect": "/api/v1/integrations/oauth/callback",
        "publish_key": "linkedin",
        "provider_slug": "linkedin_organic",
    },
    "youtube": {
        "stack": "integrations",
        "client_id_env": "YOUTUBE_CLIENT_ID",
        "client_secret_env": "YOUTUBE_CLIENT_SECRET",
        "redirect": "/api/v1/integrations/oauth/callback",
        "publish_key": "youtube",
        "provider_slug": "youtube",
    },
    "pinterest": {
        "stack": "integrations",
        "client_id_env": "PINTEREST_APP_ID",
        "client_secret_env": "PINTEREST_APP_SECRET",
        "redirect": "/api/v1/integrations/oauth/callback",
        "publish_key": "pinterest",
        "provider_slug": "pinterest",
    },
    "google_business_profile": {
        "stack": "integrations",
        "client_id_env": "GOOGLE_GBP_CLIENT_ID",
        "client_secret_env": "GOOGLE_GBP_CLIENT_SECRET",
        "redirect": "/api/v1/integrations/oauth/callback",
        "publish_key": "google_business_profile",
        "provider_slug": "google_business_profile",
    },
}


def _env(name: str) -> str:
    import os

    return (os.environ.get(name) or "").strip()


def _configured(client_id: str, client_secret: str) -> bool:
    return bool(
        client_id
        and client_secret
        and not client_id.endswith("replace_me")
        and client_id != ""
    )


async def verify() -> list[PlatformReport]:
    from aicmo.config import get_settings
    from aicmo.db.session import SessionLocal
    import aicmo.modules.integrations.providers  # noqa: F401 — register providers
    from aicmo.modules.integrations.registry import IntegrationRegistry
    from aicmo.modules.publishing.publishers import (
        publish_facebook,
        publish_google_business_profile,
        publish_instagram,
        publish_linkedin,
        publish_pinterest,
        publish_youtube,
    )
    from aicmo.modules.publishing.schemas import PublishPlatform
    from aicmo.modules.publishing import service as pub_service
    from aicmo.providers.social.registry import get_social_provider
    from sqlalchemy import func, select, text

    settings = get_settings()
    token_key = settings.integration_token_key
    public_base = settings.public_base_url or "http://localhost:3000"
    api_base = _env("NEXT_PUBLIC_API_URL") or "http://localhost:8000"

    publishers = {
        "instagram": publish_instagram,
        "facebook": publish_facebook,
        "linkedin": publish_linkedin,
        "youtube": publish_youtube,
        "pinterest": publish_pinterest,
        "google_business_profile": publish_google_business_profile,
    }

    # Scheduler
    from aicmo.queue.worker import WorkerSettings

    cron_names = [
        getattr(c, "name", "") or getattr(getattr(c, "coroutine", None), "__name__", "")
        for c in WorkerSettings.cron_jobs
    ]
    scheduler_ok = any("publish_due_cron" in str(n) for n in cron_names)

    reports: list[PlatformReport] = []

    async with SessionLocal() as session:
        # DB connectivity
        try:
            await session.execute(text("SELECT 1"))
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            db_ok = False
            db_err = str(exc)[:120]

        social_rows = []
        integration_rows = []
        if db_ok:
            from aicmo.modules.social.models import SocialConnection
            from aicmo.modules.integrations.models import (
                IntegrationConnection,
                IntegrationCredential,
            )

            social_rows = (
                await session.execute(select(SocialConnection))
            ).scalars().all()
            integration_rows = (
                await session.execute(select(IntegrationConnection))
            ).scalars().all()
            cred_count = (
                await session.execute(select(func.count()).select_from(IntegrationCredential))
            ).scalar_one()

        for name, cfg in PLATFORMS.items():
            r = PlatformReport(
                platform=name,
                oauth_status="UNKNOWN",
                connection_status="UNKNOWN",
                publishing_status="UNKNOWN",
                scheduler_status="OK" if scheduler_ok else "MISSING",
            )

            # A. OAuth config
            cid = _env(cfg["client_id_env"]) or _env(cfg.get("fallback_id", ""))
            csec = _env(cfg["client_secret_env"]) or _env(cfg.get("fallback_secret", ""))
            if name == "instagram":
                try:
                    prov = get_social_provider("instagram")
                    oauth_avail = prov.available()
                except Exception:
                    oauth_avail = False
            else:
                slug = cfg["provider_slug"]
                prov = IntegrationRegistry.get(slug)
                oauth_avail = prov.info().available

            redirect_uri = (
                f"{api_base}{cfg['redirect']}"
                if cfg["stack"] == "integrations"
                else f"{api_base}{cfg['redirect']}"
            )

            if not _configured(cid, csec):
                r.oauth_status = "NOT_CONFIGURED"
                r.issues.append(
                    f"Missing OAuth credentials: {cfg['client_id_env']} / {cfg['client_secret_env']}"
                )
                r.severity = Severity.BLOCKER
            elif not oauth_avail:
                r.oauth_status = "PROVIDER_UNAVAILABLE"
                r.issues.append("Provider.available() is False despite env vars")
                r.severity = max(r.severity, Severity.HIGH, key=lambda x: list(Severity).index(x))
            else:
                r.oauth_status = "CONFIGURED"

            if not token_key:
                r.issues.append("INTEGRATION_TOKEN_KEY not set — tokens cannot be encrypted")
                r.severity = Severity.BLOCKER
            else:
                r.evidence.append("INTEGRATION_TOKEN_KEY present")

            r.evidence.append(f"redirect_uri={redirect_uri}")
            r.evidence.append(f"public_base_url={public_base}")

            # B/C. DB connections + encryption
            if not db_ok:
                r.connection_status = "DB_UNAVAILABLE"
                r.issues.append(f"Database unreachable: {db_err}")
                r.severity = Severity.BLOCKER
            elif name == "instagram":
                ig = [s for s in social_rows if s.platform == "instagram"]
                active = [s for s in ig if s.access_token]
                if active:
                    r.connection_status = "CONNECTED"
                    tok = active[0].access_token or ""
                    from aicmo.modules.social.token_crypto import looks_encrypted

                    if looks_encrypted(tok):
                        r.evidence.append("access_token: encrypted (Fernet)")
                    else:
                        r.issues.append("Instagram access_token not encrypted")
                        r.severity = max(r.severity, Severity.HIGH, key=lambda x: list(Severity).index(x))
                    if active[0].brand_id:
                        r.evidence.append(f"brand_id={active[0].brand_id}")
                else:
                    r.connection_status = "NOT_CONNECTED"
                    if r.oauth_status == "CONFIGURED":
                        r.issues.append("OAuth configured but no active connection in DB")
            else:
                slug = cfg["provider_slug"]
                conns = [c for c in integration_rows if c.provider_slug == slug]
                active_conns = [c for c in conns if c.state == "ACTIVE"]
                if active_conns:
                    r.connection_status = "CONNECTED"
                    c = active_conns[0]
                    r.evidence.append(
                        f"account={c.external_account_name}, state={c.state}, last_sync={c.last_sync_at}"
                    )
                    if db_ok:
                        cred = (
                            await session.execute(
                                select(IntegrationCredential).where(
                                    IntegrationCredential.connection_id == c.id
                                )
                            )
                        ).scalar_one_or_none()
                        if cred:
                            if cred.encrypted_access_token:
                                r.evidence.append("access_token: encrypted (bytes)")
                            if cred.encrypted_refresh_token:
                                r.evidence.append("refresh_token: stored encrypted")
                            if cred.token_expires_at:
                                r.evidence.append(f"expires_at={cred.token_expires_at}")
                        else:
                            r.issues.append("ACTIVE connection missing credential row")
                            r.severity = max(r.severity, Severity.HIGH, key=lambda x: list(Severity).index(x))
                else:
                    r.connection_status = "NOT_CONNECTED"
                    if r.oauth_status == "CONFIGURED":
                        r.issues.append("OAuth configured but no ACTIVE connection")

            # D. Publishing path
            pub_fn = publishers.get(cfg["publish_key"])
            if pub_fn is None:
                r.publishing_status = "NO_PUBLISHER"
                r.issues.append("No publish function registered")
                r.severity = max(r.severity, Severity.BLOCKER, key=lambda x: list(Severity).index(x))
            else:
                r.publishing_status = "PUBLISHER_EXISTS"
                r.evidence.append(f"publisher={pub_fn.__name__}")

            if hasattr(pub_service, "MAX_PUBLISH_ATTEMPTS"):
                r.evidence.append(f"max_attempts={pub_service.MAX_PUBLISH_ATTEMPTS}")

            # Publish platform literal
            try:
                from aicmo.modules.publishing.schemas import SchedulePostRequest
                import uuid as _uuid

                SchedulePostRequest(
                    content_asset_id=_uuid.uuid4(),
                    platform=cfg["publish_key"],  # type: ignore[arg-type]
                    scheduled_at=datetime.now(UTC),
                )
                r.evidence.append("PublishPlatform schema accepts platform key")
            except Exception as exc:  # noqa: BLE001
                r.issues.append(f"PublishPlatform schema reject: {exc}")
                r.severity = max(r.severity, Severity.BLOCKER, key=lambda x: list(Severity).index(x))

            if r.connection_status != "CONNECTED":
                r.issues.append("Live publish not testable — no OAuth connection")
                if r.publishing_status == "PUBLISHER_EXISTS":
                    r.publishing_status = "UNTESTED_NO_CONNECTION"

            if not scheduler_ok:
                r.issues.append("publish_due_cron not registered in Arq worker")
                r.severity = max(r.severity, Severity.HIGH, key=lambda x: list(Severity).index(x))

            if r.severity == Severity.NONE and r.issues:
                r.severity = Severity.MEDIUM
            reports.append(r)

    return reports


def main() -> int:
    reports = asyncio.run(verify())
    print(json.dumps([r.__dict__ for r in reports], indent=2, default=str))
    print("\n" + "=" * 80)
    print(f"{'Platform':<22} {'OAuth':<18} {'Connection':<16} {'Publish':<22} {'Scheduler':<10} {'Severity'}")
    print("-" * 80)
    for r in reports:
        print(
            f"{r.platform:<22} {r.oauth_status:<18} {r.connection_status:<16} "
            f"{r.publishing_status:<22} {r.scheduler_status:<10} {r.severity.value}"
        )
        for issue in r.issues:
            print(f"  ⚠ {issue}")
    blockers = sum(1 for r in reports if r.severity == Severity.BLOCKER)
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
