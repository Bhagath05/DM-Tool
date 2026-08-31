"""Render an :class:`AdvisorAnalyticsSignal` into compact LLM prompt text.

Pure and DB-free so it can be unit-tested exhaustively. It emits ONLY the
computed numbers already in the signal plus a hard instruction that the model
must not alter or invent any metric, value, percentage, platform, or period —
this is the guardrail behind "the LLM explains facts, it never calculates them".
No raw DB rows, no provider responses, no tokens/secrets.
"""

from __future__ import annotations

from aicmo.modules.marketing_analytics.schemas import (
    AdvisorAnalyticsSignal,
    MetricEvidence,
)

_HEADER = (
    "=== MARKETING ANALYTICS SIGNAL (computed facts — cite exactly, never alter or invent) ==="
)


def _fmt_value(unit: str | None, value: float | None) -> str:
    if value is None:
        return "n/a"
    if unit == "ratio":
        return f"{value * 100:.1f}%"
    if unit == "rating":
        return f"{value:.1f}"
    return f"{round(value):,}"


def _fmt_pct(pct: float | None) -> str:
    if pct is None:
        return "no prior-period baseline yet"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.0f}%"


def _evidence_line(e: MetricEvidence) -> str:
    if e.change_percent is not None:
        return f"  - {e.label}: {_fmt_pct(e.change_percent)} (over {e.window})"
    if e.current is not None:
        # No comparison yet — report the level, forbid a trend claim.
        return f"  - {e.label}: currently {round(e.current):,} (no prior-period baseline yet — do not claim a trend)"
    return f"  - {e.label}: n/a"


def signal_to_prompt_block(signal: AdvisorAnalyticsSignal) -> str:
    """Compact, computed-only marketing-analytics context for the advisor prompt."""
    lines: list[str] = [
        _HEADER,
        f"Data sufficiency: {signal.data_sufficiency} ({signal.window} window).",
    ]

    if not signal.has_data:
        lines.append(signal.empty_message or "No marketing-platform metrics available.")
        lines.append(
            "Do NOT claim any account-level trend or number — there is no computed "
            "account-level evidence. Guide the user to connect an account or wait for data."
        )
        # Per-content evidence can exist even without account-level metrics.
        if _render_content(signal, lines):
            lines.append(
                "For the content findings above, use ONLY those numbers — never invent or "
                "change a metric, value, percentage, platform, or period."
            )
        return "\n".join(lines)

    if signal.empty_message:  # has data but not enough history for weekly trends
        lines.append(signal.empty_message)
        lines.append("Report only current levels below; do NOT claim week-over-week trends.")

    for p in signal.platforms:
        # Prefer metrics that have a real comparison; fall back to levels.
        shown = [m for m in p.metrics if m.change_percent is not None] or p.metrics
        if not shown:
            continue
        lines.append(f"{p.platform}:")
        for e in shown:
            lines.append(_evidence_line(e))

    if signal.insights:
        lines.append(
            "Computed insights (already evidence-checked — you may rephrase, not renumber):"
        )
        for i in signal.insights:
            lines.append(f"  - [{i.severity}] {i.observation} → {i.recommendation}")

    _render_content(signal, lines)

    lines.append(
        "Use ONLY the numbers above. Never invent or change a metric, value, percentage, "
        "platform, or time period. If a number is not listed, do not state it."
    )
    return "\n".join(lines)


def _render_content(signal: AdvisorAnalyticsSignal, lines: list[str]) -> bool:
    """Append per-content findings (Phase 5). Returns True if anything was added
    so the caller knows whether to add the content guardrail."""
    added = False
    if signal.content_insights:
        lines.append("Content-level findings (specific posts/formats — cite exactly):")
        for i in signal.content_insights:
            lines.append(f"  - [{i.severity}] {i.observation} → {i.recommendation}")
        added = True
    if signal.top_content:
        top = signal.top_content[0]
        lines.append(
            f"Top content so far: {top.platform_label} {top.asset_type} "
            f"(engagement rate {top.engagement_rate * 100:.1f}%)."
        )
        added = True
    return added
