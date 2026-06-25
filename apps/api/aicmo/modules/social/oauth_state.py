"""Signed OAuth state for social platform connect flows."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta

from aicmo.modules.integrations.crypto import InvalidIntegrationToken, decrypt, encrypt


class InvalidSocialOAuthState(ValueError):
    pass


_TTL = timedelta(minutes=10)


def issue(*, user_id: str, brand_id: str, platform: str) -> str:
    payload = {
        "uid": user_id,
        "bid": brand_id,
        "platform": platform,
        "nonce": secrets.token_urlsafe(16),
        "exp": (datetime.now(UTC) + _TTL).timestamp(),
    }
    return encrypt(json.dumps(payload, separators=(",", ":"))).decode("ascii")


def verify(state: str) -> tuple[str, str, str]:
    """Returns (user_id, brand_id, platform)."""
    if not state:
        raise InvalidSocialOAuthState("Missing OAuth state.")
    try:
        raw = decrypt(state.encode("ascii"))
        payload = json.loads(raw)
    except (InvalidIntegrationToken, json.JSONDecodeError) as exc:
        raise InvalidSocialOAuthState("Invalid OAuth state.") from exc
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or datetime.now(UTC).timestamp() > exp:
        raise InvalidSocialOAuthState("OAuth state expired.")
    uid = payload.get("uid")
    bid = payload.get("bid")
    platform = payload.get("platform")
    if not all(isinstance(x, str) for x in (uid, bid, platform)):
        raise InvalidSocialOAuthState("OAuth state incomplete.")
    return uid, bid, platform
