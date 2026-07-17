"""Background discovery runner.

Runs as a FastAPI BackgroundTask (in-process, own DB session) — the same
pattern as onboarding analysis, so no Redis/Arq is required. Fetches the
website (or reads the from-scratch seed), asks the LLM for a structured
Brand Brain draft, and records the result on the discovery row. Failures
are stored on the row, never re-raised.
"""

from __future__ import annotations

import structlog
from sqlalchemy import update

from aicmo.db.session import SessionLocal
from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.discovery import fetcher
from aicmo.modules.discovery.models import WebsiteDiscovery
from aicmo.modules.discovery.prompts import (
    DISCOVERY_SYSTEM,
    build_scratch_prompt,
    build_website_prompt,
)
from aicmo.modules.discovery.schemas import DiscoveryDraft

log = structlog.get_logger()


async def run_discovery(discovery_id: str) -> None:
    """Entry point scheduled as a BackgroundTask."""
    try:
        async with SessionLocal() as session:
            row = await session.get(WebsiteDiscovery, discovery_id)
            if row is None:
                return
            row.status = "running"
            await session.commit()
            source = row.source
            url = row.url
            business_name = row.business_name
            industry = row.industry or ""
            seed = row.seed or {}
    except Exception as e:
        log.warning("discovery.run_setup_failed", id=discovery_id, error=str(e))
        return

    try:
        if source == "website":
            await _set_stage(discovery_id, "reading")
            signals = await _discover_website(url or "")
            await _set_stage(discovery_id, "understanding")
            prompt = build_website_prompt(
                business_name=business_name, industry=industry, signals=signals
            )
        else:
            signals = None
            prompt = build_scratch_prompt(seed=seed)

        await _set_stage(discovery_id, "building")
        router = get_llm_router()
        result = await router.generate(
            response_schema=DiscoveryDraft,
            system=DISCOVERY_SYSTEM,
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.5,
            max_tokens=3500,
        )
        await _mark_completed(discovery_id, signals, result.data)
        log.info(
            "discovery.completed",
            id=discovery_id,
            source=source,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )
    except fetcher.DiscoveryFetchError as e:
        await _mark_failed(discovery_id, str(e))
    except Exception as e:
        log.warning("discovery.failed", id=discovery_id, error=str(e)[:200])
        await _mark_failed(
            discovery_id,
            "We couldn't finish learning about your business. Please try again.",
        )


async def _set_stage(discovery_id: str, stage: str) -> None:
    """Advance the real progress marker the UI timeline reads."""
    try:
        async with SessionLocal() as session:
            await session.execute(
                update(WebsiteDiscovery)
                .where(WebsiteDiscovery.id == discovery_id)
                .values(stage=stage)
            )
            await session.commit()
    except Exception as e:
        log.warning("discovery.stage_update_failed", stage=stage, error=str(e)[:120])


async def _discover_website(url: str) -> dict:
    final_url, html = await fetcher.fetch_website(url)
    return fetcher.extract_signals(html, final_url)


async def _mark_completed(
    discovery_id: str, signals: dict | None, draft: DiscoveryDraft
) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(WebsiteDiscovery)
            .where(WebsiteDiscovery.id == discovery_id)
            .values(
                status="completed",
                stage="done",
                signals=signals,
                draft=draft.model_dump(mode="json"),
                error=None,
            )
        )
        await session.commit()


async def _mark_failed(discovery_id: str, message: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(WebsiteDiscovery)
            .where(WebsiteDiscovery.id == discovery_id)
            .values(status="failed", error=message[:500])
        )
        await session.commit()
