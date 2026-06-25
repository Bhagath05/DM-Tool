"""FastAPI dependency for the ARQ pool — Phase 0.

Request handlers that enqueue background work depend on `get_arq_pool`
and pass the result to `enqueue_tenant_job`. Returns None when jobs are
disabled or Redis was unavailable at startup; callers treat enqueue as
best-effort.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


async def get_arq_pool(request: Request) -> Any | None:
    return getattr(request.app.state, "arq_pool", None)
