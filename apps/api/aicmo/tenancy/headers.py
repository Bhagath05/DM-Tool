"""Header parsing — X-Organization-Id and X-Brand-Id.

Both are optional at the HTTP level — `require_tenant` decides whether
their absence is an error based on context (org-only route vs. brand
route, single-membership auto-resolve, last-active-brand fallback).
"""

from __future__ import annotations

import uuid

from fastapi import Request

from aicmo.tenancy.exceptions import MissingTenant

ORG_HEADER = "X-Organization-Id"
BRAND_HEADER = "X-Brand-Id"


def parse_org_header(request: Request) -> uuid.UUID | None:
    raw = request.headers.get(ORG_HEADER)
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as e:
        raise MissingTenant(detail=f"Invalid {ORG_HEADER} header") from e


def parse_brand_header(request: Request) -> uuid.UUID | None:
    raw = request.headers.get(BRAND_HEADER)
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as e:
        raise MissingTenant(detail=f"Invalid {BRAND_HEADER} header") from e
