"""Phase 10.2c — Service-layer pure logic without a DB.

Pins the two pieces of business logic that don't require Postgres:

  1. ALLOWED_CLIENT_EVENTS — exhaustive lock on which event types the
     internal recorder accepts.
  2. _parse_clerk_ts        — tolerant timestamp parsing.
  3. _to_session_read       — current-flag derivation.

End-to-end DB-backed flows (record_event, register_session, revoke)
are exercised by the smoke test against the real dev database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from aicmo.modules.security import service

# ---------------------------------------------------------------------
#  ALLOWED_CLIENT_EVENTS
# ---------------------------------------------------------------------


class TestAllowedClientEvents:
    def test_failed_login_and_mfa_only(self) -> None:
        """The frontend can ONLY post these two event types. Login,
        logout, password_change, session_revoke must come from the
        Clerk webhook — accepting them from clients would let a user
        forge admin-attributed events in their own timeline."""
        assert service.ALLOWED_CLIENT_EVENTS == frozenset({"failed_login", "mfa_challenge"})

    def test_login_is_NOT_client_postable(self) -> None:
        """If this fails, someone added 'login' to the allowlist — that
        means a client can forge a successful-login event without
        actually logging in. Review carefully."""
        assert "login" not in service.ALLOWED_CLIENT_EVENTS

    def test_session_revoke_is_NOT_client_postable(self) -> None:
        assert "session_revoke" not in service.ALLOWED_CLIENT_EVENTS

    def test_password_change_is_NOT_client_postable(self) -> None:
        assert "password_change" not in service.ALLOWED_CLIENT_EVENTS


# ---------------------------------------------------------------------
#  _to_session_read — current-flag + active-flag logic
# ---------------------------------------------------------------------


class TestToSessionRead:
    """Maps a first-party `user_sessions` row to the API SessionRead. `is_current`
    is derived from the caller's session id (the row's own uuid, as a string)."""

    @staticmethod
    def _row(
        *,
        row_id: uuid.UUID | None = None,
        revoked_at: datetime | None = None,
        expires_at: datetime | None = None,
    ):
        row = MagicMock()
        row.id = row_id or uuid.uuid4()
        row.user_agent = "Mozilla/5.0"
        row.ip = None
        row.last_used_at = datetime(2026, 6, 5, tzinfo=UTC)
        row.expires_at = expires_at
        row.revoked_at = revoked_at
        row.created_at = datetime(2026, 6, 1, tzinfo=UTC)
        return row

    def test_current_session_flagged(self) -> None:
        now = datetime(2026, 6, 5, tzinfo=UTC)
        rid = uuid.uuid4()
        row = self._row(row_id=rid, expires_at=now + timedelta(days=7))
        read = service._to_session_read(row, str(rid), now)
        assert read.is_current is True
        assert read.is_active is True

    def test_non_current_session_not_flagged(self) -> None:
        now = datetime(2026, 6, 5, tzinfo=UTC)
        row = self._row()
        read = service._to_session_read(row, str(uuid.uuid4()), now)
        assert read.is_current is False

    def test_no_current_id_means_none_is_current(self) -> None:
        now = datetime(2026, 6, 5, tzinfo=UTC)
        row = self._row()
        read = service._to_session_read(row, None, now)
        assert read.is_current is False

    def test_revoked_session_is_inactive(self) -> None:
        now = datetime(2026, 6, 5, tzinfo=UTC)
        row = self._row(revoked_at=now - timedelta(hours=1))
        read = service._to_session_read(row, None, now)
        assert read.is_active is False

    def test_expired_session_is_inactive(self) -> None:
        """A session past its expires_at is inactive even if not explicitly revoked."""
        now = datetime(2026, 6, 5, tzinfo=UTC)
        row = self._row(expires_at=now - timedelta(minutes=1))
        read = service._to_session_read(row, None, now)
        assert read.is_active is False

    def test_future_expiry_is_active(self) -> None:
        now = datetime(2026, 6, 5, tzinfo=UTC)
        row = self._row(expires_at=now + timedelta(days=7))
        read = service._to_session_read(row, None, now)
        assert read.is_active is True


# ---------------------------------------------------------------------
#  Suspicious-signal heuristic constant
# ---------------------------------------------------------------------


def test_suspicious_threshold_is_three_failed_logins() -> None:
    """If you tighten this to 1, you'll alarm-fatigue the founder out
    of the security page. If you loosen to 10, you'll miss a brute force.
    3 is the spec; pin it."""
    assert service.SUSPICIOUS_FAILED_LOGINS_24H == 3
