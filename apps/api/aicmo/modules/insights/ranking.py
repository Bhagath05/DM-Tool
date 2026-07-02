"""Module 7 — pure ranking / dedupe / grouping for the Insights Feed.

No I/O, no LLM — deterministic transforms over already-collected FeedItems.
"""

from __future__ import annotations

import hashlib
import re

from aicmo.modules.insights.schemas import FeedGroup, FeedItem, Severity

_SEVERITY_WEIGHT: dict[str, float] = {
    "critical": 1.0,
    "high": 0.75,
    "medium": 0.5,
    "low": 0.25,
}
_SEVERITY_RANK: dict[str, int] = {"critical": 3, "high": 2, "medium": 1, "low": 0}
_URGENCY_WEIGHT: dict[str, float] = {
    "now": 1.0,
    "this_week": 0.7,
    "this_month": 0.4,
    "monitor": 0.2,
}
_IMPACT_WEIGHT: dict[str, float] = {
    "revenue": 1.0,
    "customer": 0.9,
    "lead": 0.85,
    "cost": 0.6,
    "time": 0.5,
}


def severity_from_confidence(confidence: int | None, *, negative: bool = False) -> Severity:
    """Map a 0-100 confidence to a severity band. A negative lesson (something
    that failed / is hurting) is bumped up a band — those matter more."""
    c = confidence if confidence is not None else 50
    if negative:
        if c >= 60:
            return "critical"
        return "high"
    if c >= 80:
        return "high"
    if c >= 55:
        return "medium"
    return "low"


def compute_priority(item: FeedItem) -> float:
    """0-1 composite: severity dominates, then urgency, confidence, impact."""
    sev = _SEVERITY_WEIGHT.get(item.severity, 0.5)
    urg = _URGENCY_WEIGHT.get(item.urgency or "", 0.3)
    conf = (item.confidence if item.confidence is not None else 50) / 100.0
    imp = _IMPACT_WEIGHT.get(item.impact_category or "", 0.5)
    return round(0.40 * sev + 0.25 * urg + 0.20 * conf + 0.15 * imp, 4)


def make_id(source_module: str, category: str, title: str) -> str:
    """Stable id from source+category+normalised title (also the dedupe basis)."""
    norm = _normalise_title(title)
    raw = f"{source_module}|{category}|{norm}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _normalise_title(title: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", "", title.lower())
    t = re.sub(r"\s+", " ", t).strip()
    return t[:80]


def _dedupe_key(item: FeedItem) -> str:
    """Cross-source dedupe: same category + very similar title collapse, even if
    two different modules surfaced the same idea."""
    return f"{item.category}|{_normalise_title(item.title)}"


def dedupe(items: list[FeedItem]) -> list[FeedItem]:
    """Collapse near-duplicate insights, keeping the highest-priority
    representative and recording the merged ids on it."""
    best: dict[str, FeedItem] = {}
    for it in items:
        key = _dedupe_key(it)
        cur = best.get(key)
        if cur is None:
            best[key] = it
            continue
        winner, loser = (it, cur) if it.priority_score > cur.priority_score else (cur, it)
        merged = set(winner.related_ids) | set(loser.related_ids) | {loser.id}
        merged.discard(winner.id)
        winner.related_ids = sorted(merged)
        # Prefer the winner but keep the loser's evidence if the winner lacks any.
        if not winner.evidence and loser.evidence:
            winner.evidence = loser.evidence
        best[key] = winner
    return list(best.values())


def rank(items: list[FeedItem]) -> list[FeedItem]:
    """Highest priority first; stable tiebreak on severity then title."""
    return sorted(
        items,
        key=lambda i: (
            i.priority_score,
            _SEVERITY_RANK.get(i.severity, 1),
            -len(i.title),
        ),
        reverse=True,
    )


def group(items: list[FeedItem]) -> list[FeedGroup]:
    """Group by category, ordered by the group's most severe member."""
    buckets: dict[str, list[FeedItem]] = {}
    for it in items:
        buckets.setdefault(it.group_key, []).append(it)
    groups: list[FeedGroup] = []
    for key, members in buckets.items():
        top = max(members, key=lambda m: _SEVERITY_RANK.get(m.severity, 1))
        groups.append(
            FeedGroup(
                key=key,
                label=key.replace("_", " ").title(),
                top_severity=top.severity,
                item_ids=[m.id for m in members],
            )
        )
    groups.sort(key=lambda g: _SEVERITY_RANK.get(g.top_severity, 1), reverse=True)
    return groups


def meets_min_severity(item: FeedItem, minimum: str) -> bool:
    return _SEVERITY_RANK.get(item.severity, 1) >= _SEVERITY_RANK.get(minimum, 0)
