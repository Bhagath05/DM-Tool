"""Integration framework — service layer.

Brand-scoped (tenant-aware) orchestration around the
`IntegrationConnection` + `IntegrationCredential` tables.

Every public function:
  - Filters by `tenant.organization_id` (and `brand_id` where relevant).
  - Routes state transitions through `state.assert_transition()`.
  - Encrypts tokens before persisting (`crypto.encrypt`).
  - NEVER returns a token, even by accident — token decryption is
    only done inside this module's `with_access_token()` helper.

The router is a thin shell over this file.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aicmo.modules.integrations import crypto, oauth_state, state
from aicmo.modules.audit import service as audit_service
from aicmo.modules.integrations.models import (
    IntegrationConnection,
    IntegrationCredential,
)
from aicmo.modules.integrations.providers.base import (
    IntegrationProvider,
    OAuthTokens,
    SyncResult,
)
from aicmo.modules.integrations.providers.stubs import NotYetAvailable
from aicmo.modules.integrations.registry import (
    IntegrationRegistry,
    UnknownProvider,
)
from aicmo.modules.integrations.schemas import (
    CatalogEntry,
    ConnectionRead,
    ConnectionState,
)
from aicmo.tenancy.context import TenantContext


T = TypeVar("T")


# ---------------------------------------------------------------------
#  Catalog — what shows up on GET /integrations
# ---------------------------------------------------------------------


async def build_catalog(
    session: AsyncSession, *, tenant: TenantContext
) -> list[CatalogEntry]:
    """Pair every registered provider with the active brand's current
    connection (if any). Stable order: registry order.

    NOTE: catalog is brand-scoped — we read connections that match
    either (org_id, brand_id) for brand-level providers OR
    (org_id, NULL) for org-level providers. Phase 10.2a doesn't
    distinguish the two on the read path; that lands when the first
    org-level CRM connector ships.
    """
    rows = await session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.organization_id == tenant.organization_id,
            (
                (IntegrationConnection.brand_id == tenant.brand_id)
                | (IntegrationConnection.brand_id.is_(None))
            ),
        )
    )
    by_slug: dict[str, IntegrationConnection] = {}
    for row in rows.scalars():
        # If multiple non-terminal rows somehow exist (shouldn't, per
        # the partial unique index), prefer the most recently updated.
        existing = by_slug.get(row.provider_slug)
        if existing is None or row.updated_at > existing.updated_at:
            by_slug[row.provider_slug] = row

    catalog: list[CatalogEntry] = []
    for provider in IntegrationRegistry.all():
        conn = by_slug.get(provider.slug)
        catalog.append(
            CatalogEntry(
                provider=provider.info(),
                connection=(
                    ConnectionRead.model_validate(conn) if conn else None
                ),
            )
        )
    return catalog


async def get_provider_detail(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    slug: str,
) -> CatalogEntry:
    provider = IntegrationRegistry.get(slug)  # raises UnknownProvider → 404
    conn = await _load_connection_by_slug(session, tenant=tenant, slug=slug)
    return CatalogEntry(
        provider=provider.info(),
        connection=ConnectionRead.model_validate(conn) if conn else None,
    )


# ---------------------------------------------------------------------
#  Connect — start an OAuth attempt
# ---------------------------------------------------------------------


async def start_connect(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    slug: str,
    redirect_uri: str,
) -> tuple[IntegrationConnection, str]:
    """Create (or reuse) a connection row in PENDING_AUTH state and
    return `(connection, authorize_url)`. Caller redirects to the URL.

    Idempotent: hitting connect twice in a row for the same provider
    reuses the existing PENDING_AUTH row instead of failing on the
    partial unique index.
    """
    provider = IntegrationRegistry.get(slug)

    existing = await _load_connection_by_slug(session, tenant=tenant, slug=slug)
    if existing is not None and existing.state == "ACTIVE":
        # Reconnecting on top of an ACTIVE connection — disconnect first
        # so the founder can't accidentally orphan a valid set of tokens.
        # Surface as 409 via the router; the UI can prompt "disconnect
        # the existing connection first?".
        raise AlreadyConnected(slug=slug, connection_id=existing.id)

    if existing is not None:
        # Re-use the row from a previous failed / expired attempt.
        state.assert_transition(existing.state, "PENDING_AUTH")
        conn = existing
        conn.state = "PENDING_AUTH"
        conn.error_message = None
    else:
        conn = IntegrationConnection(
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
            provider_slug=slug,
            state="PENDING_AUTH",
            created_by_user_id=tenant.user_uuid,
        )
        session.add(conn)
        try:
            await session.flush()
        except IntegrityError as exc:  # pragma: no cover — defensive
            await session.rollback()
            raise AlreadyConnected(slug=slug, connection_id=None) from exc

    state_token = oauth_state.issue(conn.id)
    try:
        authorize_url = await provider.authorize_url(
            state=state_token, redirect_uri=redirect_uri
        )
    except NotYetAvailable as exc:
        # Stub provider — roll back the PENDING_AUTH row so we don't
        # leave junk in the DB just because the founder hit a button
        # for a connector we haven't built yet.
        await session.rollback()
        raise ProviderNotReady(slug=slug, message=str(exc)) from exc

    await session.commit()
    await session.refresh(conn)
    return conn, authorize_url


# ---------------------------------------------------------------------
#  Callback — exchange code, mark ACTIVE
# ---------------------------------------------------------------------


async def handle_callback(
    session: AsyncSession,
    *,
    state_token: str,
    code: str,
    redirect_uri: str,
) -> IntegrationConnection:
    """The OAuth provider has redirected the founder back to us.
    Verify the state, exchange the code, persist encrypted tokens,
    flip to ACTIVE.

    No tenant arg: the state token carries the connection id; the
    connection row carries the tenant. This is the only public
    function in the service layer that doesn't take a TenantContext
    — the OAuth callback isn't an authenticated tenant-bearing call,
    it's a redirect from the third party.
    """
    connection_id = oauth_state.verify(state_token)
    conn = await session.get(IntegrationConnection, connection_id)
    if conn is None:
        raise UnknownConnection(connection_id=connection_id)

    provider = IntegrationRegistry.get(conn.provider_slug)
    try:
        state.assert_transition(conn.state, "ACTIVE")
        tokens = await provider.exchange_code(code, redirect_uri)
        account = await provider.fetch_account_info(tokens.access_token)
    except NotYetAvailable as exc:
        await _fail_to_error(session, conn, str(exc))
        raise ProviderNotReady(slug=conn.provider_slug, message=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — protocol-level errors all flow here
        await _fail_to_error(session, conn, repr(exc))
        raise

    # Persist encrypted credential.
    await _replace_credential(session, conn=conn, tokens=tokens)

    conn.state = "ACTIVE"
    conn.external_account_id = account.external_account_id
    conn.external_account_name = account.external_account_name
    conn.scopes_granted = list(account.scopes_granted)
    conn.connected_at = datetime.now(timezone.utc)
    conn.error_message = None
    await session.commit()
    await session.refresh(conn)
    log.info(
        "integration.connected",
        provider_slug=conn.provider_slug,
        connection_id=str(conn.id),
        organization_id=str(conn.organization_id),
        brand_id=str(conn.brand_id) if conn.brand_id else None,
    )
    return conn


# ---------------------------------------------------------------------
#  Disconnect — terminal state
# ---------------------------------------------------------------------


async def disconnect(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    connection_id: uuid.UUID,
) -> IntegrationConnection:
    """User-initiated disconnect. Drops credentials, sets state to
    DISCONNECTED. Idempotent: calling on an already-DISCONNECTED row
    is a no-op."""
    conn = await _load_owned_connection(
        session, tenant=tenant, connection_id=connection_id
    )

    if conn.state == "DISCONNECTED":
        return conn  # idempotent — keep the audit-friendly trail row

    state.assert_transition(conn.state, "DISCONNECTED")
    await session.execute(
        IntegrationCredential.__table__.delete().where(
            IntegrationCredential.connection_id == conn.id
        )
    )
    conn.state = "DISCONNECTED"
    conn.error_message = None
    if tenant.user_uuid:
        await audit_service.record(
            session,
            organization_id=tenant.organization_id,
            actor_user_id=tenant.user_uuid,
            action="integration.disconnected",
            brand_id=conn.brand_id,
            target_type="integration_connection",
            target_id=conn.id,
            metadata={"provider_slug": conn.provider_slug},
        )
    await session.commit()
    await session.refresh(conn)
    log.info(
        "integration.disconnected",
        provider_slug=conn.provider_slug,
        connection_id=str(conn.id),
        organization_id=str(tenant.organization_id),
    )
    return conn


# ---------------------------------------------------------------------
#  Sync — caller-initiated pull
# ---------------------------------------------------------------------


async def sync(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    connection_id: uuid.UUID,
) -> SyncResult:
    conn = await _load_owned_connection(
        session, tenant=tenant, connection_id=connection_id
    )
    if conn.state != "ACTIVE":
        raise NotConnectable(
            connection_id=conn.id,
            current_state=conn.state,
            message="Connection isn't ACTIVE — reconnect first.",
        )

    provider = IntegrationRegistry.get(conn.provider_slug)
    started = datetime.now(timezone.utc)
    try:
        access_token = await _read_access_token(session, conn, provider=provider)
        result = await provider.sync(
            connection_id=conn.id,
            access_token=access_token,
            external_account_id=conn.external_account_id,
        )
    except NotYetAvailable as exc:
        await _fail_to_error(session, conn, str(exc))
        raise ProviderNotReady(slug=conn.provider_slug, message=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await _fail_to_error(session, conn, repr(exc))
        raise

    if result.metrics and conn.brand_id:
        from aicmo.modules.advisor.connectors import upsert_metric

        period_end = result.period_end or result.finished_at
        raw_map = result.metric_raw or {}
        for key, value in result.metrics.items():
            await upsert_metric(
                session,
                brand_id=conn.brand_id,
                provider_slug=conn.provider_slug,
                metric_key=key,
                metric_value=float(value),
                period_end=period_end,
                raw_json=raw_map.get(key, {"source": "integration_sync"}),
            )

    conn.last_sync_at = result.finished_at or datetime.now(timezone.utc)
    if result.error_message:
        conn.state = "ERROR"
        conn.error_message = result.error_message
        conn.last_error_at = conn.last_sync_at
    else:
        conn.error_message = None
    if tenant.user_uuid:
        await audit_service.record(
            session,
            organization_id=tenant.organization_id,
            actor_user_id=tenant.user_uuid,
            action="integration.synced",
            brand_id=conn.brand_id,
            target_type="integration_connection",
            target_id=conn.id,
            metadata={
                "provider_slug": conn.provider_slug,
                "rows_pulled": result.rows_pulled,
                "error": result.error_message,
            },
        )
    await session.commit()
    await session.refresh(conn)
    _ = started  # reserved for future telemetry
    return result


# ---------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------


async def _load_connection_by_slug(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    slug: str,
) -> IntegrationConnection | None:
    """Find the brand's current connection for a given provider. Prefers
    the non-terminal row (the partial unique index makes at most one
    non-terminal possible)."""
    rows = await session.execute(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.organization_id == tenant.organization_id,
            (
                (IntegrationConnection.brand_id == tenant.brand_id)
                | (IntegrationConnection.brand_id.is_(None))
            ),
            IntegrationConnection.provider_slug == slug,
        )
        .order_by(IntegrationConnection.updated_at.desc())
    )
    return rows.scalars().first()


async def _load_owned_connection(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    connection_id: uuid.UUID,
) -> IntegrationConnection:
    conn = await session.get(IntegrationConnection, connection_id)
    if conn is None or conn.organization_id != tenant.organization_id:
        raise UnknownConnection(connection_id=connection_id)
    return conn


async def _replace_credential(
    session: AsyncSession,
    *,
    conn: IntegrationConnection,
    tokens: OAuthTokens,
) -> None:
    """Replace any prior credential row with a fresh encrypted one."""
    await session.execute(
        IntegrationCredential.__table__.delete().where(
            IntegrationCredential.connection_id == conn.id
        )
    )
    cred = IntegrationCredential(
        connection_id=conn.id,
        encrypted_access_token=crypto.encrypt(tokens.access_token),
        encrypted_refresh_token=(
            crypto.encrypt(tokens.refresh_token)
            if tokens.refresh_token
            else None
        ),
        token_expires_at=tokens.expires_at,
        encrypted_raw_response=(
            crypto.encrypt(tokens.raw_response)
            if tokens.raw_response
            else None
        ),
        rotated_at=datetime.now(timezone.utc),
    )
    session.add(cred)


async def _read_access_token(
    session: AsyncSession,
    conn: IntegrationConnection,
    *,
    provider: IntegrationProvider | None = None,
) -> str:
    """Internal helper — decrypts and refreshes access tokens when expired."""
    cred = await session.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.connection_id == conn.id
        )
    )
    if cred is None:
        if conn.state == "ACTIVE":
            conn.state = "ERROR"
            conn.error_message = "Connection has no stored credentials — reconnect."
            conn.last_error_at = datetime.now(timezone.utc)
            await session.commit()
        raise NotConnectable(
            connection_id=conn.id,
            current_state=conn.state,
            message="Connection has no stored credentials.",
        )

    now = datetime.now(timezone.utc)
    expires = cred.token_expires_at
    needs_refresh = (
        expires is not None
        and expires <= now + timedelta(minutes=5)
        and cred.encrypted_refresh_token is not None
    )
    if needs_refresh:
        if provider is None:
            provider = IntegrationRegistry.get(conn.provider_slug)
        refresh_plain = crypto.decrypt(cred.encrypted_refresh_token)
        tokens = await provider.refresh(refresh_plain)
        await _replace_credential(session, conn=conn, tokens=tokens)
        log.info(
            "integration.token_refreshed",
            provider_slug=conn.provider_slug,
            connection_id=str(conn.id),
        )
        return tokens.access_token

    return crypto.decrypt(cred.encrypted_access_token)


async def _fail_to_error(
    session: AsyncSession,
    conn: IntegrationConnection,
    message: str,
) -> None:
    """Roll the connection to ERROR, persist the error message, commit.
    Caller still raises whatever exception triggered this — we just
    record it durably before the request unwinds."""
    conn.state = "ERROR"
    conn.error_message = message[:500]  # never let provider blobs balloon
    conn.last_error_at = datetime.now(timezone.utc)
    await session.commit()


# ---------------------------------------------------------------------
#  Service-level exceptions
# ---------------------------------------------------------------------


class AlreadyConnected(RuntimeError):
    """Trying to start a new connect attempt while an ACTIVE one
    exists. Router → 409."""

    def __init__(self, *, slug: str, connection_id: uuid.UUID | None):
        self.slug = slug
        self.connection_id = connection_id
        super().__init__(
            f"Provider {slug!r} already has an active connection; "
            f"disconnect first."
        )


class UnknownConnection(LookupError):
    """No connection with that id is reachable from the active tenant.
    Router → 404."""

    def __init__(self, *, connection_id: uuid.UUID):
        self.connection_id = connection_id
        super().__init__(f"Connection {connection_id} not found.")


class NotConnectable(RuntimeError):
    """Connection exists but isn't in a state that supports the
    requested action. Router → 409."""

    def __init__(
        self,
        *,
        connection_id: uuid.UUID,
        current_state: ConnectionState,
        message: str,
    ):
        self.connection_id = connection_id
        self.current_state = current_state
        super().__init__(message)


class ProviderNotReady(RuntimeError):
    """Provider exists in the registry but hasn't implemented the
    OAuth methods yet. Router → 501 with a founder-friendly
    "Coming soon" message."""

    def __init__(self, *, slug: str, message: str):
        self.slug = slug
        super().__init__(message)


async def ensure_access_token(
    session: AsyncSession,
    conn: IntegrationConnection,
) -> str:
    """Public wrapper for publish/sync — decrypts and refreshes when needed."""
    provider = IntegrationRegistry.get(conn.provider_slug)
    return await _read_access_token(session, conn, provider=provider)


# Re-export so the router can `from .service import UnknownProvider`
# without piercing into the registry module. UnknownProvider is the
# "no such slug" error; the four above are operational errors.
__all__ = [
    "build_catalog",
    "get_provider_detail",
    "start_connect",
    "handle_callback",
    "disconnect",
    "sync",
    "ensure_access_token",
    "AlreadyConnected",
    "UnknownConnection",
    "NotConnectable",
    "ProviderNotReady",
    "UnknownProvider",
]
