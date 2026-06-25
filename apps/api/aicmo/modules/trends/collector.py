"""Fetches trend signals from free, no-key sources.

Sources:
- Google Trends via pytrends (sync — wrapped in asyncio.to_thread)
- Reddit via the public *.json endpoints (no auth required, just a UA)

Both calls are best-effort: a failure on one source still returns partial
data. The analyzer downstream is resilient to empty signals.
"""

from __future__ import annotations

import asyncio
import re

import httpx
import structlog
from pytrends.request import TrendReq

from aicmo.modules.trends.schemas import (
    GoogleTrendItem,
    RawTrends,
    RedditTrendItem,
)

log = structlog.get_logger()

_REDDIT_UA = "ai-cmo-mvp/0.1 (trend collector)"
_REDDIT_TIMEOUT = 8.0
_PYTRENDS_TIMEOUT = (5, 10)  # (connect, read)
_KEYWORD_LIMIT = 4  # cap pytrends fan-out to keep us under their rate limit


# ----------------- public entry point -----------------


async def collect(keywords: list[str], reddit_query: str) -> RawTrends:
    keywords = _normalise_keywords(keywords)
    google_task = asyncio.create_task(_safe_google(keywords))
    reddit_task = asyncio.create_task(_safe_reddit(reddit_query))

    google_trends, google_err = await google_task
    reddit_posts, reddit_err = await reddit_task

    attempted = ["google_trends", "reddit"]
    failed = [name for name, err in (("google_trends", google_err), ("reddit", reddit_err)) if err]

    return RawTrends(
        google_trends=google_trends,
        reddit_posts=reddit_posts,
        sources_attempted=attempted,
        sources_failed=failed,
    )


# ----------------- Google Trends -----------------


async def _safe_google(keywords: list[str]) -> tuple[list[GoogleTrendItem], str | None]:
    if not keywords:
        return [], "no_keywords"
    try:
        items = await asyncio.to_thread(_fetch_google_sync, keywords)
        return items, None
    except Exception as e:  # noqa: BLE001 — pytrends throws many exception types
        log.warning("trends.google_failed", error=str(e))
        return [], str(e)


def _fetch_google_sync(keywords: list[str]) -> list[GoogleTrendItem]:
    pytrends = TrendReq(hl="en-US", tz=0, timeout=_PYTRENDS_TIMEOUT)
    items: list[GoogleTrendItem] = []

    # pytrends accepts up to 5 keywords per build_payload, but querying each
    # individually gets us cleaner related/rising data per keyword.
    for kw in keywords:
        try:
            pytrends.build_payload([kw], timeframe="now 7-d")
            related = pytrends.related_queries().get(kw) or {}
        except Exception as e:  # noqa: BLE001
            log.warning("trends.google_keyword_failed", keyword=kw, error=str(e))
            continue

        top_df = related.get("top")
        rising_df = related.get("rising")
        top = (
            [str(q) for q in top_df["query"].tolist()][:10]
            if top_df is not None and not top_df.empty
            else []
        )
        rising = (
            [str(q) for q in rising_df["query"].tolist()][:10]
            if rising_df is not None and not rising_df.empty
            else []
        )
        items.append(
            GoogleTrendItem(keyword=kw, related_queries=top, rising_queries=rising)
        )

    return items


# ----------------- Reddit -----------------


async def _safe_reddit(query: str) -> tuple[list[RedditTrendItem], str | None]:
    if not query.strip():
        return [], "no_query"
    try:
        return await _fetch_reddit(query), None
    except Exception as e:  # noqa: BLE001
        log.warning("trends.reddit_failed", error=str(e))
        return [], str(e)


async def _fetch_reddit(query: str) -> list[RedditTrendItem]:
    url = "https://www.reddit.com/search.json"
    params = {"q": query, "sort": "hot", "t": "week", "limit": 25}
    async with httpx.AsyncClient(
        timeout=_REDDIT_TIMEOUT, headers={"User-Agent": _REDDIT_UA}
    ) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

    children = payload.get("data", {}).get("children", [])
    items: list[RedditTrendItem] = []
    for c in children:
        d = c.get("data", {})
        title = d.get("title")
        sub = d.get("subreddit")
        if not title or not sub:
            continue
        items.append(
            RedditTrendItem(
                subreddit=str(sub),
                title=str(title)[:280],
                score=int(d.get("score", 0)),
                num_comments=int(d.get("num_comments", 0)),
                url=f"https://reddit.com{d.get('permalink', '')}",
            )
        )
    return items


# ----------------- helpers -----------------


def _normalise_keywords(keywords: list[str]) -> list[str]:
    seen: list[str] = []
    for raw in keywords:
        cleaned = re.sub(r"\s+", " ", raw.strip().lower())
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
        if len(seen) >= _KEYWORD_LIMIT:
            break
    return seen
