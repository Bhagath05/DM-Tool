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
from datetime import datetime, timedelta, timezone
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
        assert service.ALLOWED_CLIENT_EVENTS == frozenset(
            {"failed_login", "mfa_challenge"}
        )

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
#  _parse_clerk_ts
# ---------------------------------------------------------------------


class TestParseClerkTs:
    def test_milliseconds_epoch_parsed(self) -> None:
        # 2026-06-05T00:00:00Z = 1780617600 seconds
        ts_ms = 1780617600000
        result = service._parse_clerk_ts(ts_ms)
        assert result is not None
        assert result.year == 2026
        assert result.tzinfo == timezone.utc

    def test_none_returns_none(self) -> None:
        assert service._parse_clerk_ts(None) is None

    def test_string_int_works(self) -> None:
        # Clerk sometimes sends as string — we tolerate.
        assert service._parse_clerk_ts("1780617600000") is not None

    def test_garbage_returns_none(self) -> None:
        assert service._parse_clerk_ts("not-a-ts") is None
        assert service._parse_clerk_ts({"weird": "thing"}) is None

    def test_overflow_returns_none(self) -> None:
        """A spec-violating gigantic value must not crash the dispatcher."""
        assert service._parse_clerk_ts(10**30) is None


# ---------------------------------------------------------------------
#  _to_session_read — current-flag + active-flag logic
# ---------------------------------------------------------------------


class TestToSessionRead:
    @staticmethod
    def _row(
        *,
        clerk_session_id: str = "sess_abc",
        revoked_at: datetime | None = None,
        expires_at: datetime | None = None,
    ):
        row = MagicMock()
        row.id = uuid.uuid4()
        row.clerk_session_id = clerk_session_id
        row.user_agent = "Mozilla/5.0"
        row.ip_address = None
        row.geo_country = None
        row.geo_city = None
        row.last_seen_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
        row.expires_at = expires_at
        row.revoked_at = revoked_at
        row.revoked_by = "user" if revoked_at else None
        row.revocation_status = "remote_ok" if revoked_at else None
        row.created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
        return row

    def test_current_session_flagged(self) -> None:
        now = datetime(2026, 6, 5, tzinfo=timezone.utc)
        row = self._row(clerk_session_id="sess_xyz")
        read = service._to_session_read(row, "sess_xyz", now)
        assert read.is_current is True
        assert read.is_active is True

    def test_non_current_session_not_flagged(self) -> None:
        now = datetime(2026, 6, 5, tzinfo=timezone.utc)
        row = self._row(clerk_session_id="sess_aaa")
        read = service._to_session_read(row, "sess_bbb", now)
        assert read.is_current is False

    def test_no_current_id_means_none_is_current(self) -> None:
        now = datetime(2026, 6, 5, tzinfo=timezone.utc)
        row = self._row()
        read = service._to_session_read(row, None, now)
        assert read.is_current is False

    def test_revoked_session_is_inactive(self) -> None:
        now = datetime(2026, 6, 5, tzinfo=timezone.utc)
        row = self._row(revoked_at=now - timedelta(hours=1))
        read = service._to_session_read(row, None, now)
        assert read.is_active is False
        assert read.revoked_by == "user"

    def test_expired_session_is_inactive(self) -> None:
        """A session past its expires_at is inactive even if not explicitly revoked."""
        now = datetime(2026, 6, 5, tzinfo=timezone.utc)
        row = self._row(expires_at=now - timedelta(minutes=1))
        read = service._to_session_read(row, None, now)
        assert read.is_active is False

    def test_future_expiry_is_active(self) -> None:
        now = datetime(2026, 6, 5, tzinfo=timezone.utc)
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
