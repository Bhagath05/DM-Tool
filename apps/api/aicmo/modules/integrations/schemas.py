"""Pydantic surfaces for the integration framework — Phase 10.2a.

Hard rule: **no schema in this file references a token field.** The
encrypted credential lives in its own table and never crosses the API
boundary. If you need to add a field that contains a secret, add it
to `models.IntegrationCredential` only, not here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Lock-step with:
#   apps/api/alembic/versions/0022_integrations.py (_CONNECTION_STATES)
#   apps/web/src/lib/api.ts (Phase 10.2g)
ConnectionState = Literal[
    "DISCONNECTED",
    "PENDING_AUTH",
    "ACTIVE",
    "EXPIRED",
    "ERROR",
    "SUSPENDED",
]

ProviderCategory = Literal["ads", "crm", "analytics", "social", "local"]


# ---------------------------------------------------------------------
#  Provider catalog — static metadata about each integration
# ---------------------------------------------------------------------


class ProviderInfo(BaseModel):
    """Static description of an integration provider — what shows up
    in the catalog before any connection is made."""

    model_config = ConfigDict(frozen=True)

    slug: str
    display_name: str
    category: ProviderCategory
    icon_id: str  # frontend maps to inline SVG
    description: str
    scopes: list[str] = Field(default_factory=list)
    # `available` is true when the provider is fully implemented.
    # Phase 10.2a ships all six as stubs, so this is uniformly false
    # until Phase 11 lights Meta Ads up.
    available: bool = False


# ---------------------------------------------------------------------
#  Connection — the public-API view of a tenant's connection state
# ---------------------------------------------------------------------


class ConnectionRead(BaseModel):
    """Everything the founder is allowed to see about a connection."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    brand_id: uuid.UUID | None
    provider_slug: str
    state: ConnectionState
    external_account_id: str | None
    external_account_name: str | None
    scopes_granted: list[str]
    error_message: str | None
    connected_at: datetime | None
    last_sync_at: datetime | None
    last_error_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CatalogEntry(BaseModel):
    """One row in the GET /integrations catalog — pairs the static
    provider info with the tenant's current connection (if any)."""

    provider: ProviderInfo
    connection: ConnectionRead | None


class CatalogResponse(BaseModel):
    items: list[CatalogEntry]


# ---------------------------------------------------------------------
#  Action responses
# ---------------------------------------------------------------------


class ConnectResponse(BaseModel):
    """POST /integrations/{slug}/connect — handed back to the browser
    which then redirects to `authorize_url`. `connection_id` is the
    PENDING_AUTH row we just created."""

    connection_id: uuid.UUID
    authorize_url: str
    state: ConnectionState  # always PENDING_AUTH on success


class HealthResponse(BaseModel):
    """GET /integrations/{conn_id}/health — minimal, no token data."""

    connection_id: uuid.UUID
    provider_slug: str
    state: ConnectionState
    last_sync_at: datetime | None
    last_error_at: datetime | None
    error_message: str | None


class SyncResponse(BaseModel):
    """POST /integrations/{conn_id}/sync — what the provider returned."""

    connection_id: uuid.UUID
    state: ConnectionState
    started_at: datetime
    finished_at: datetime
    rows_pulled: int = 0
    error_message: str | None = None
