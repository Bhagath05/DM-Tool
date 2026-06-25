"""Resolve Clerk user profile fields for identity reconciliation."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from aicmo.config import get_settings

log = structlog.get_logger()

PENDING_EMAIL_SUFFIX = "@pending.local"


def profile_from_claims(claims: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Best-effort email / display name / avatar from a verified JWT."""
    email: str | None = None
    raw_email = claims.get("email")
    if isinstance(raw_email, str) and "@" in raw_email:
        email = raw_email.strip().lower()

    first = claims.get("first_name") or claims.get("given_name")
    last = claims.get("last_name") or claims.get("family_name")
    name = claims.get("name") or claims.get("full_name")
    display_name: str | None = None
    if isinstance(name, str) and name.strip():
        display_name = name.strip()
    elif isinstance(first, str) or isinstance(last, str):
        display_name = " ".join(
            p.strip() for p in (first or "", last or "") if isinstance(p, str) and p.strip()
        ) or None

    avatar = (
        claims.get("image_url")
        or claims.get("picture")
        or claims.get("profile_image_url")
    )
    avatar_url = avatar if isinstance(avatar, str) and avatar.startswith("http") else None

    return email, display_name, avatar_url


async def fetch_clerk_user_profile(
    clerk_user_id: str,
) -> tuple[str | None, str | None, str | None]:
    """Fetch primary email + name from Clerk when JWT claims are sparse."""
    secret = (get_settings().clerk_secret_key or "").strip()
    if not secret or secret.startswith("sk_test_replace"):
        return None, None, None

    url = f"https://api.clerk.com/v1/users/{clerk_user_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {secret}"},
            )
        if resp.status_code != 200:
            log.warning(
                "clerk.profile_fetch_failed",
                clerk_user_id=clerk_user_id,
                status=resp.status_code,
            )
            return None, None, None
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("clerk.profile_fetch_error", clerk_user_id=clerk_user_id, error=str(exc))
        return None, None, None

    email: str | None = None
    emails = data.get("email_addresses") or []
    primary_id = data.get("primary_email_address_id")
    for entry in emails:
        if not isinstance(entry, dict):
            continue
        addr = entry.get("email_address")
        if isinstance(addr, str) and "@" in addr:
            if primary_id and entry.get("id") == primary_id:
                email = addr.strip().lower()
                break
            if email is None:
                email = addr.strip().lower()

    first = data.get("first_name")
    last = data.get("last_name")
    display_name: str | None = None
    if isinstance(first, str) or isinstance(last, str):
        display_name = " ".join(
            p.strip() for p in (first or "", last or "") if isinstance(p, str) and p.strip()
        ) or None

    avatar = data.get("image_url")
    avatar_url = avatar if isinstance(avatar, str) and avatar.startswith("http") else None
    return email, display_name, avatar_url


def is_placeholder_email(email: str | None) -> bool:
    if not email:
        return True
    return email.endswith(PENDING_EMAIL_SUFFIX)
