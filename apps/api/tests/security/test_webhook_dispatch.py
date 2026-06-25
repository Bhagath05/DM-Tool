"""Phase 10.2c — Webhook dispatcher logic.

Tests the routing layer: given a verified payload, what does the
service decide to do? Specifically:

  session.created    → 'login' event + session register attempt
  session.ended      → 'logout' event + session marked revoked
  session.removed    → 'logout' event + session marked revoked
  session.revoked    → 'session_revoke' event (DIFFERENT type) + marked
  user.updated       → 'password_change' event ONLY when recent ts present
  unknown event      → 200 with {handled: false}, NO event recorded

The DB layer is stubbed; we assert on the dispatcher's decisions, not
on Postgres state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from aicmo.modules.security import service


# ---------------------------------------------------------------------
#  Stub session that records every record_event call + tracks updates
# ---------------------------------------------------------------------


@dataclass
class _RecordedEvent:
    event_type: str
    user_id: Any
    clerk_session_id: str | None
    actor: str
    metadata: dict[str, Any]


@pytest.fixture
def fake_session(monkeypatch):
    """Replace the service's DB-touching functions with stubs that
    just record what would have happened. Returns a context object
    with `recorded_events: list[_RecordedEvent]` for assertions."""
    recorded: list[_RecordedEvent] = []

    async def fake_record_event(
        _sess,
        *,
        event_type,
        user_id,
        organization_id=None,
        clerk_session_id=None,
        actor="self",
        ip_address=None,
        user_agent=None,
        metadata=None,
        occurred_at=None,
    ):
        recorded.append(
            _RecordedEvent(
                event_type=event_type,
                user_id=user_id,
                clerk_session_id=clerk_session_id,
                actor=actor,
                metadata=metadata or {},
            )
        )
        return MagicMock(id="evt_test")

    async def fake_register(
        _sess,
        *,
        user_id,
        clerk_session_id,
        user_agent=None,
        ip_address=None,
        geo_country=None,
        geo_city=None,
        expires_at=None,
    ):
        row = MagicMock()
        row.id = "row_test"
        row.user_id = user_id
        row.clerk_session_id = clerk_session_id
        return row

    monkeypatch.setattr(service, "record_event", fake_record_event)
    monkeypatch.setattr(service, "register_or_touch_session", fake_register)

    return type("Ctx", (), {"recorded": recorded, "session": MagicMock()})()


# ---------------------------------------------------------------------
#  Helpers: fake _resolve_user
# ---------------------------------------------------------------------


def _make_fake_user(user_uuid):
    user = MagicMock()
    user.id = user_uuid
    return user


# ---------------------------------------------------------------------
#  session.created
# ---------------------------------------------------------------------


class TestSessionCreated:
    @pytest.mark.asyncio
    async def test_records_login_event(self, fake_session, monkeypatch) -> None:
        user_uuid = "user-uuid-1"
        monkeypatch.setattr(
            service, "_resolve_user", AsyncMock(return_value=_make_fake_user(user_uuid))
        )
        payload = {
            "type": "session.created",
            "data": {
                "id": "sess_abc",
                "user_id": "user_clerk_1",
                "user_agent": "Firefox",
                "expire_at": int(time.time() * 1000) + 86400000,
            },
        }
        result = await service.dispatch_webhook(
            fake_session.session, payload=payload, ip_address="1.2.3.4"
        )
        assert result["handled"] is True
        login_events = [
            e for e in fake_session.recorded if e.event_type == "login"
        ]
        assert len(login_events) == 1
        assert login_events[0].clerk_session_id == "sess_abc"
        assert login_events[0].actor == "self"

    @pytest.mark.asyncio
    async def test_unknown_user_records_system_event(
        self, fake_session, monkeypatch
    ) -> None:
        """If the webhook arrives before the user is lazy-created, we
        still log a system-actor event so the timeline isn't silently
        empty."""
        monkeypatch.setattr(service, "_resolve_user", AsyncMock(return_value=None))
        payload = {
            "type": "session.created",
            "data": {"id": "sess_x", "user_id": "user_unknown"},
        }
        result = await service.dispatch_webhook(
            fake_session.session, payload=payload, ip_address=None
        )
        assert result["handled"] is False
        # System-actor login event recorded with user_id=None
        assert len(fake_session.recorded) == 1
        e = fake_session.recorded[0]
        assert e.event_type == "login"
        assert e.user_id is None
        assert e.actor == "system"
        assert e.metadata["clerk_user_id"] == "user_unknown"

    @pytest.mark.asyncio
    async def test_missing_ids_short_circuits(self, fake_session) -> None:
        payload = {"type": "session.created", "data": {}}
        result = await service.dispatch_webhook(
            fake_session.session, payload=payload
        )
        assert result == {"handled": False, "reason": "missing_ids"}
        assert fake_session.recorded == []


# ---------------------------------------------------------------------
#  session.ended / removed / revoked
# ---------------------------------------------------------------------


class TestSessionTerminated:
    @pytest.mark.asyncio
    async def test_session_ended_records_logout(
        self, fake_session, monkeypatch
    ) -> None:
        # No matching row in DB → still records the event, with user_id=None.
        monkeypatch.setattr(
            service.select,
            "__call__",
            lambda *a, **kw: MagicMock(where=lambda *a, **kw: MagicMock()),
        )
        # Stub session.execute to return no row.
        fake_session.session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=lambda: None)
        )

        payload = {"type": "session.ended", "data": {"id": "sess_q"}}
        result = await service.dispatch_webhook(
            fake_session.session, payload=payload
        )
        assert result["handled"] is True
        events = fake_session.recorded
        assert len(events) == 1
        assert events[0].event_type == "logout"
        assert events[0].clerk_session_id == "sess_q"
        assert events[0].metadata["clerk_event"] == "session.ended"

    @pytest.mark.asyncio
    async def test_session_revoked_uses_revoke_event_type(
        self, fake_session
    ) -> None:
        """`session.revoked` is DIFFERENT from `session.ended` —
        it means someone explicitly killed the session. Use the
        `session_revoke` event type so the audit log distinguishes
        a clean logout from a forced revoke."""
        fake_session.session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=lambda: None)
        )
        payload = {"type": "session.revoked", "data": {"id": "sess_killed"}}
        result = await service.dispatch_webhook(
            fake_session.session, payload=payload
        )
        assert result["handled"] is True
        events = fake_session.recorded
        assert len(events) == 1
        assert events[0].event_type == "session_revoke"

    @pytest.mark.asyncio
    async def test_session_removed_treated_as_logout(self, fake_session) -> None:
        fake_session.session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=lambda: None)
        )
        payload = {"type": "session.removed", "data": {"id": "sess_r"}}
        result = await service.dispatch_webhook(fake_session.session, payload=payload)
        assert result["handled"] is True
        assert fake_session.recorded[0].event_type == "logout"

    @pytest.mark.asyncio
    async def test_missing_session_id_short_circuits(self, fake_session) -> None:
        payload = {"type": "session.ended", "data": {}}
        result = await service.dispatch_webhook(fake_session.session, payload=payload)
        assert result == {"handled": False, "reason": "missing_session_id"}


# ---------------------------------------------------------------------
#  user.updated → password_change (heuristic)
# ---------------------------------------------------------------------


class TestUserUpdated:
    @pytest.mark.asyncio
    async def test_recent_password_change_emits_event(
        self, fake_session, monkeypatch
    ) -> None:
        user_uuid = "u1"
        monkeypatch.setattr(
            service,
            "_resolve_user",
            AsyncMock(return_value=_make_fake_user(user_uuid)),
        )
        # password_last_updated_at = 30s ago
        ts_ms = (int(time.time()) - 30) * 1000
        payload = {
            "type": "user.updated",
            "data": {
                "id": "user_clerk_abc",
                "password_last_updated_at": ts_ms,
            },
        }
        result = await service.dispatch_webhook(fake_session.session, payload=payload)
        assert result["handled"] is True
        events = fake_session.recorded
        assert len(events) == 1
        assert events[0].event_type == "password_change"

    @pytest.mark.asyncio
    async def test_stale_password_update_NOT_emitted(self, fake_session) -> None:
        """user.updated fires for many reasons. A 1-hour-old
        password_last_updated_at means the update wasn't the password
        — don't emit a phantom security event."""
        ts_ms = (int(time.time()) - 3600) * 1000
        payload = {
            "type": "user.updated",
            "data": {
                "id": "user_x",
                "password_last_updated_at": ts_ms,
            },
        }
        result = await service.dispatch_webhook(fake_session.session, payload=payload)
        assert result["handled"] is False
        assert result["reason"] == "password_update_too_old"
        assert fake_session.recorded == []

    @pytest.mark.asyncio
    async def test_no_password_ts_means_not_a_password_change(
        self, fake_session
    ) -> None:
        payload = {
            "type": "user.updated",
            "data": {"id": "u", "name": "new name"},
        }
        result = await service.dispatch_webhook(fake_session.session, payload=payload)
        assert result["reason"] == "not_a_password_change"
        assert fake_session.recorded == []


# ---------------------------------------------------------------------
#  Unknown event types
# ---------------------------------------------------------------------


class TestUnknownEvents:
    @pytest.mark.asyncio
    async def test_unknown_type_returns_handled_false_but_no_error(
        self, fake_session
    ) -> None:
        """Tolerance: a Clerk feature addition must not 400 the webhook
        (which would back up Clerk's retry queue). Log + ack."""
        payload = {"type": "session.future_thing", "data": {}}
        result = await service.dispatch_webhook(fake_session.session, payload=payload)
        assert result["handled"] is False
        assert "unknown_event_type" in result["reason"]
        assert fake_session.recorded == []

    @pytest.mark.asyncio
    async def test_user_lifecycle_events_acked_silently(
        self, fake_session
    ) -> None:
        """`user.created` / `user.deleted` are handled elsewhere
        (users module). We must ack cleanly without emitting security
        events — otherwise every signup creates a phantom row."""
        for t in ("user.created", "user.deleted"):
            payload = {"type": t, "data": {"id": "u"}}
            result = await service.dispatch_webhook(
                fake_session.session, payload=payload
            )
            assert result["handled"] is False
            assert result["reason"] == "user_lifecycle_handled_elsewhere"
        assert fake_session.recorded == []
