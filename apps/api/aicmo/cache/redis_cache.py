"""Thin Redis JSON cache for expensive read endpoints."""

from __future__ import annotations

import json
from typing import Any

import structlog

from aicmo.config import get_settings

log = structlog.get_logger()

_CLIENT = None


async def _client():
    global _CLIENT  # noqa: PLW0603
    if _CLIENT is None:
        import redis.asyncio as redis  # noqa: PLC0415

        _CLIENT = redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
        )
    return _CLIENT


async def cache_get(key: str) -> dict[str, Any] | None:
    try:
        client = await _client()
        raw = await client.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("cache.get_failed", key=key, error=str(exc))
        return None


async def cache_set(key: str, value: dict[str, Any], *, ttl_seconds: int) -> None:
    try:
        client = await _client()
        await client.setex(key, ttl_seconds, json.dumps(value))
    except Exception as exc:  # noqa: BLE001
        log.warning("cache.set_failed", key=key, error=str(exc))
