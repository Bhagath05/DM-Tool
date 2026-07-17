"""AI Marketing Health — plain-language scores for the AI headquarters.

Every score is computed from REAL rows already in this brand's database
(Brand Brain completeness, content produced, leads captured, ads made,
connected accounts, lead pages). Nothing is estimated or invented; if there's
no data the score is honestly low and the recommendation says what to do
about it.

Deterministic on purpose — no LLM call. These render instantly on the
dashboard, cost nothing, and can't hallucinate a number. The advisor's
LLM-authored narrative recommendations live in `intelligence.py`; this is
the "is my marketing healthy, and what should I fix first?" layer.

Per the product constitution every score carries: what it means, why it
matters, whether it's good or bad, and what to do next.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.ads.models import GeneratedAd
from aicmo.modules.advisor.schemas import HealthScore, MarketingHealthResponse
from aicmo.modules.content.models import GeneratedContent
from aicmo.modules.integrations.models import IntegrationConnection
from aicmo.modules.landing_pages.models import LandingPage
from aicmo.modules.leads.models import Lead
from aicmo.modules.onboarding.schemas import BusinessProfileResponse

_WINDOW_DAYS = 30
# 3 pieces a week is the cadence the platform coaches toward.
_CONTENT_TARGET = 12
_LEADS_TARGET = 10


def _status(score: int) -> str:
    if score >= 70:
        return "good"
    if score >= 40:
        return "watch"
    return "bad"


def brand_completeness(profile: BusinessProfileResponse) -> int:
    """Share of the Brand Brain that's filled in. Mirrors what the Brand
    Brain page shows the owner, computed from the same columns."""
    checks = [
        bool(profile.business_name),
        bool(profile.website),
        bool(profile.industry),
        bool(profile.target_audience),
        bool(profile.brand_tone),
        bool(profile.writing_style),
        bool(profile.pricing),
        bool(profile.products),
        bool(profile.services),
        bool(profile.unique_selling_points),
        bool(profile.competitors),
        bool(profile.goals),
        bool(profile.keywords),
        bool(profile.brand_colors),
        bool(profile.fonts),
        bool(profile.brand_rules),
    ]
    return round(sum(1 for c in checks if c) / len(checks) * 100)


async def _count(session: AsyncSession, model, brand_id, since=None) -> int:
    stmt = select(func.count()).select_from(model).where(model.brand_id == brand_id)
    if since is not None:
        stmt = stmt.where(model.created_at >= since)
    return int((await session.execute(stmt)).scalar_one() or 0)


async def compute_health(
    session: AsyncSession, *, profile: BusinessProfileResponse
) -> MarketingHealthResponse:
    brand_id = profile.brand_id
    since = datetime.now(UTC) - timedelta(days=_WINDOW_DAYS)

    content_30d = await _count(session, GeneratedContent, brand_id, since)
    leads_30d = await _count(session, Lead, brand_id, since)
    ads_total = await _count(session, GeneratedAd, brand_id)
    pages_total = await _count(session, LandingPage, brand_id)
    connections = await _count(session, IntegrationConnection, brand_id)

    scores: list[HealthScore] = []

    # --- Brand -------------------------------------------------------
    brand = brand_completeness(profile)
    scores.append(
        HealthScore(
            key="brand",
            label="Your brand",
            score=brand,
            status=_status(brand),
            explanation=(
                f"We know about {brand}% of what makes your business you — "
                "your products, customers, voice and look."
            ),
            why=(
                "Everything we write and design for you is built from this. "
                "The more we know, the more it sounds like you."
            ),
            recommendation=(
                "Your brand details look complete. Nothing to do here."
                if brand >= 70
                else "Fill in the gaps in your Brand Brain — it takes 2 minutes and improves everything we make."
            ),
        )
    )

    # --- Content -----------------------------------------------------
    content = min(100, round(content_30d / _CONTENT_TARGET * 100))
    scores.append(
        HealthScore(
            key="content",
            label="Your content",
            score=content,
            status=_status(content),
            explanation=(
                f"You've made {content_30d} piece{'' if content_30d == 1 else 's'} "
                "of content in the last 30 days."
            ),
            why="Businesses that post regularly stay top of mind and get found more often.",
            recommendation=(
                "You're posting at a healthy pace. Keep it up."
                if content >= 70
                else "Aim for about 3 pieces a week — we can create a month's worth for you in one go."
            ),
        )
    )

    # --- Website -----------------------------------------------------
    website = (50 if profile.website else 0) + (50 if pages_total > 0 else 0)
    scores.append(
        HealthScore(
            key="website",
            label="Your website",
            score=website,
            status=_status(website),
            explanation=(
                "You have a website and a page set up to collect enquiries."
                if website >= 100
                else "You have a website, but no page set up to collect enquiries."
                if profile.website
                else "We don't have a website on file for you yet."
            ),
            why="This is where interested people go to buy or get in touch.",
            recommendation=(
                "Your website setup looks good."
                if website >= 70
                else "Add your website in your Brand Brain."
                if not profile.website
                else "Create a simple page that collects enquiries, so visitors can reach you."
            ),
        )
    )

    # --- Getting found (SEO, in plain words) -------------------------
    found = (50 if profile.keywords else 0) + (50 if pages_total > 0 else 0)
    scores.append(
        HealthScore(
            key="getting_found",
            label="Getting found online",
            score=found,
            status=_status(found),
            explanation=(
                "We know the words your customers search for, and you have pages that can show up."
                if found >= 100
                else "We don't yet know all the words your customers search for."
            ),
            why="When people search for what you sell, you want to be what they find.",
            recommendation=(
                "You're set up to be found. Publishing more helps you climb."
                if found >= 70
                else "Add the words customers would search for to your Brand Brain, then publish pages that use them."
            ),
        )
    )

    # --- Advertising -------------------------------------------------
    advertising = (60 if ads_total > 0 else 0) + (40 if connections > 0 else 0)
    scores.append(
        HealthScore(
            key="advertising",
            label="Your ads",
            score=advertising,
            status=_status(advertising),
            explanation=(
                f"You've created {ads_total} ad{'' if ads_total == 1 else 's'}"
                + (
                    " and connected an account to run them."
                    if connections > 0
                    else ", but no account is connected to run them yet."
                )
            ),
            why="Ads are the fastest way to put your business in front of new customers.",
            recommendation=(
                "Your ads are set up. Watch which ones bring enquiries and put more behind the winners."
                if advertising >= 70
                else "Create your first ad — we'll write it from your Brand Brain."
                if ads_total == 0
                else "Connect an account so your ads can actually run."
            ),
        )
    )

    # --- Leads -------------------------------------------------------
    leads = min(100, round(leads_30d / _LEADS_TARGET * 100))
    scores.append(
        HealthScore(
            key="leads",
            label="New enquiries",
            score=leads,
            status=_status(leads),
            explanation=(
                f"{leads_30d} {'person has' if leads_30d == 1 else 'people have'} "
                "reached out in the last 30 days."
            ),
            why="These are real people interested in buying from you — the point of all of it.",
            recommendation=(
                "Good flow of enquiries. Make sure you're replying quickly."
                if leads >= 70
                else "Publish a page that collects enquiries and share it — that's the quickest way to start."
            ),
        )
    )

    # --- Social presence ---------------------------------------------
    social = min(100, connections * 34)
    scores.append(
        HealthScore(
            key="social",
            label="Your social accounts",
            score=social,
            status=_status(social),
            explanation=(
                f"You have {connections} account{'' if connections == 1 else 's'} connected."
                if connections
                else "You haven't connected any social accounts yet."
            ),
            why="Connecting accounts lets us post for you and learn what your audience likes.",
            recommendation=(
                "Nicely connected. We can post for you and learn what works."
                if social >= 70
                else "Connect your main account so we can post for you and see what's working."
            ),
        )
    )

    overall = round(sum(s.score for s in scores) / len(scores))
    weakest = min(scores, key=lambda s: s.score)
    headline = (
        "Your marketing is in good shape. Keep the momentum going."
        if overall >= 70
        else f"The biggest thing holding you back right now is {weakest.label.lower()}."
        if overall >= 40
        else "Let's get the basics in place — small steps will move this fast."
    )

    return MarketingHealthResponse(
        overall=overall,
        overall_status=_status(overall),
        headline=headline,
        focus_key=weakest.key,
        scores=scores,
    )
