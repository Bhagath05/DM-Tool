"""Phase 10.2a — Signed OAuth state token.

CSRF-defence test: a state issued for connection A must not decode as
connection B. And an expired state must be rejected with a clean
`InvalidOAuthState` rather than a generic decryption error.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from aicmo.modules.integrations import crypto, oauth_state


def test_issue_then_verify_round_trips(integration_key: str) -> None:
    cid = uuid.uuid4()
    token = oauth_state.issue(cid)
    assert oauth_state.verify(token) == cid


def test_each_issue_produces_a_unique_token(integration_key: str) -> None:
    """Nonces guarantee tokens differ even when they encode the same
    connection id. Without this, an attacker who saw one valid state
    could replay it indefinitely (until expiry)."""
    cid = uuid.uuid4()
    a = oauth_state.issue(cid)
    b = oauth_state.issue(cid)
    assert a != b
    assert oauth_state.verify(a) == cid
    assert oauth_state.verify(b) == cid


def test_empty_state_rejected(integration_key: str) -> None:
    with pytest.raises(oauth_state.InvalidOAuthState, match="Missing"):
        oauth_state.verify("")


def test_tampered_state_rejected(integration_key: str) -> None:
    cid = uuid.uuid4()
    token = oauth_state.issue(cid)
    # Flip one character — Fernet's MAC catches it.
    tampered = ("A" if token[0] != "A" else "B") + token[1:]
    with pytest.raises(oauth_state.InvalidOAuthState):
        oauth_state.verify(tampered)


def test_expired_state_rejected(integration_key: str) -> None:
    """Forge a state with `exp` in the past and confirm verify rejects.
    We mint via the real `crypto.encrypt` so we know the signature is
    valid — the only thing failing the check should be the expiry."""
    expired_payload = {
        "cid": str(uuid.uuid4()),
        "nonce": "expired-test",
        "exp": (datetime.now(timezone.utc) - timedelta(seconds=1)).timestamp(),
    }
    token = crypto.encrypt(json.dumps(expired_payload)).decode("ascii")
    with pytest.raises(oauth_state.InvalidOAuthState, match="expired"):
        oauth_state.verify(token)


def test_state_with_missing_cid_rejected(integration_key: str) -> None:
    payload = {
        "nonce": "x",
        "exp": (datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp(),
    }
    token = crypto.encrypt(json.dumps(payload)).decode("ascii")
    with pytest.raises(oauth_state.InvalidOAuthState, match="connection id"):
        oauth_state.verify(token)


def test_state_with_garbage_cid_rejected(integration_key: str) -> None:
    payload = {
        "cid": "not-a-uuid",
        "nonce": "x",
        "exp": (datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp(),
    }
    token = crypto.encrypt(json.dumps(payload)).decode("ascii")
    with pytest.raises(oauth_state.InvalidOAuthState, match="invalid"):
        oauth_state.verify(token)
