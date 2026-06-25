"""Retry helper for integration HTTP calls — 429/5xx with backoff."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

T = TypeVar("T")

_RETRYABLE = {429, 500, 502, 503, 504}


async def with_retry(
    fn: Callable[[], Awaitable[httpx.Response]],
    *,
    attempts: int = 3,
    base_delay_s: float = 0.5,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = await fn()
            if resp.status_code not in _RETRYABLE or attempt == attempts - 1:
                return resp
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            if attempt == attempts - 1:
                raise
        await asyncio.sleep(base_delay_s * (2**attempt))
    if last_exc:
        raise last_exc
    raise RuntimeError("retry exhausted")
