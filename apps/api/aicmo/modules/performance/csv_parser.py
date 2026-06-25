"""CSV upload parser for Phase 9.1.

Pure functions — no DB, no IO beyond the input string. Easy to unit
test row-by-row.

We accept Meta-Ads-Manager-style headers AND a small alias set so
founders can paste lightly-edited exports. Header matching is
case-insensitive and whitespace-tolerant. Required columns:

  - some "date" column         (Date | Day | Reporting day | event_date)
  - some "creative" column     (Ad name | Creative name | Ad | creative_ref)
  - some "spend" column        (Amount spent | Spend | Cost)
  - some "impressions" column  (Impressions)
  - some "clicks" column       (Clicks (all) | Clicks (link) | Link clicks | Clicks)

Optional:
  - conversions / Results / Purchases / Leads
  - Conversion value / Purchase value / Value
  - Currency  (defaults to brand default if missing — but we surface
    a warning rather than silently picking)
  - Platform  (defaults to "meta")

Money is converted to integer *micros* immediately so we never
round-trip through float at storage.

This module deliberately does NOT call the DB — see `service.ingest_csv`
for the wiring.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Iterable

from aicmo.modules.performance.schemas import (
    CsvIngestRow,
    CsvParseError,
)

# ---------------------------------------------------------------------
#  Header alias map — lowercase -> canonical
# ---------------------------------------------------------------------

_ALIASES: dict[str, str] = {
    # date
    "date": "event_date",
    "day": "event_date",
    "reporting day": "event_date",
    "reporting starts": "event_date",
    "event_date": "event_date",
    # creative
    "ad name": "creative_ref",
    "creative name": "creative_ref",
    "ad": "creative_ref",
    "creative": "creative_ref",
    "creative_ref": "creative_ref",
    # numeric
    "impressions": "impressions",
    "impr.": "impressions",
    "impr": "impressions",
    "clicks (all)": "clicks",
    "clicks (link)": "clicks",
    "link clicks": "clicks",
    "clicks": "clicks",
    "results": "conversions",
    "purchases": "conversions",
    "leads": "conversions",
    "conversions": "conversions",
    # money
    "amount spent": "spend",
    "spend": "spend",
    "cost": "spend",
    "purchase conversion value": "conversion_value",
    "conversion value": "conversion_value",
    "purchase value": "conversion_value",
    "value": "conversion_value",
    # context
    "currency": "currency",
    "platform": "platform",
}

REQUIRED = {"event_date", "creative_ref", "impressions", "clicks", "spend"}


# ---------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------


def _normalise_header(header: str) -> str:
    """Lowercase + strip. We keep parentheses because Meta uses
    'Clicks (all)' vs 'Clicks (link)' as meaningful distinctions.
    Strips a stray UTF-8 BOM in case the caller didn't decode with
    utf-8-sig (the router does, but parse_csv stays defensive)."""
    return header.lstrip("﻿").strip().lower()


def _build_index(header_row: Iterable[str]) -> dict[str, int]:
    """Map canonical field name -> column index. Unknown headers are
    ignored (e.g. Meta exports include 20+ columns we don't read)."""
    index: dict[str, int] = {}
    for i, raw in enumerate(header_row):
        canon = _ALIASES.get(_normalise_header(raw))
        if canon and canon not in index:
            # First occurrence wins. Meta sometimes exports both
            # "Clicks (all)" and "Clicks (link)"; we prefer the
            # first match — they should pick one export shape.
            index[canon] = i
    return index


def _parse_date(value: str) -> date:
    """Accept ISO (2026-05-29) and Meta's 'Jun 1, 2026' formats."""
    value = value.strip()
    if not value:
        raise ValueError("date is empty")
    # Try ISO first (cheapest, most common).
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%b %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date format: {value!r}")


def _parse_int(value: str | None) -> int:
    """Empty / missing -> 0. Comma thousands separators allowed."""
    if value is None:
        return 0
    s = value.strip().replace(",", "")
    if not s:
        return 0
    # Meta sometimes exports "-" for missing — treat as 0.
    if s in {"-", "—"}:
        return 0
    return int(float(s))  # float() handles "120.0"


def _parse_money_micros(value: str | None) -> int:
    """Money column -> int micros. Empty/dash -> 0. Currency symbols
    stripped — currency is captured in its own column."""
    if value is None:
        return 0
    s = value.strip().replace(",", "")
    if not s or s in {"-", "—"}:
        return 0
    # Strip leading currency symbol/code (₹, $, €, INR, USD…). We
    # only need digits + decimal.
    cleaned = "".join(ch for ch in s if ch.isdigit() or ch == ".")
    if not cleaned:
        return 0
    return int(round(float(cleaned) * 1_000_000))


def _normalise_platform(value: str | None) -> str:
    if not value:
        return "meta"
    v = value.strip().lower()
    # Map common variants to our enum.
    if v in {"facebook", "ig", "instagram", "meta", "fb"}:
        return "meta"
    if v in {"google", "google ads", "adwords", "search"}:
        return "google"
    if v in {"linkedin", "li"}:
        return "linkedin"
    if v in {"tiktok", "tt"}:
        return "tiktok"
    if v in {"youtube", "yt"}:
        return "youtube"
    return "other"


def _normalise_currency(value: str | None, fallback: str | None) -> str | None:
    if value:
        s = value.strip().upper()
        # Founders sometimes write "Rs" / "Rs." for INR.
        if s in {"RS", "RS.", "₹", "INR"}:
            return "INR"
        if s in {"$", "USD"}:
            return "USD"
        if len(s) == 3 and s.isalpha():
            return s
    return fallback


# ---------------------------------------------------------------------
#  Public surface
# ---------------------------------------------------------------------


class ParseResult:
    """In-memory result of parsing a CSV blob.

    Returned by `parse_csv`. The service layer then writes accepted
    rows to performance_events and surfaces errors back to the
    founder so they can fix the file.
    """

    def __init__(
        self,
        accepted: list[CsvIngestRow],
        errors: list[CsvParseError],
        currency: str | None,
        date_range: tuple[date, date] | None,
    ) -> None:
        self.accepted = accepted
        self.errors = errors
        self.currency = currency
        self.date_range = date_range


def parse_csv(
    payload: str,
    *,
    brand_default_currency: str | None = None,
    default_platform: str = "meta",
) -> ParseResult:
    """Parse a CSV blob. Never raises for row-level problems —
    surfaces them as `CsvParseError` so the founder sees a list
    rather than a 500.

    Raises ValueError ONLY when the file's structure is unusable
    (no header, missing required columns).
    """
    reader = csv.reader(io.StringIO(payload))
    try:
        header_row = next(reader)
    except StopIteration:
        raise ValueError("CSV is empty")

    index = _build_index(header_row)
    missing = REQUIRED - index.keys()
    if missing:
        raise ValueError(
            "CSV missing required columns: " + ", ".join(sorted(missing))
        )

    accepted: list[CsvIngestRow] = []
    errors: list[CsvParseError] = []
    currency_seen: str | None = None
    date_min: date | None = None
    date_max: date | None = None

    # `enumerate(reader, start=2)` because the header was row 1.
    for row_number, raw_row in enumerate(reader, start=2):
        # Allow short rows — pad with empty strings rather than IndexError.
        if not raw_row or all(not cell.strip() for cell in raw_row):
            continue

        def get(field: str) -> str | None:
            i = index.get(field)
            if i is None or i >= len(raw_row):
                return None
            return raw_row[i]

        raw_dict = {field: (get(field) or "") for field in index}
        try:
            currency = _normalise_currency(
                get("currency"), brand_default_currency
            )
            if currency is None:
                raise ValueError(
                    "currency missing and brand has no default — "
                    "add a Currency column or set the brand currency"
                )

            event_date = _parse_date(get("event_date") or "")
            creative_ref = (get("creative_ref") or "").strip()
            if not creative_ref:
                raise ValueError("creative name is empty")

            row = CsvIngestRow(
                event_date=event_date,
                creative_ref=creative_ref[:255],
                platform=_normalise_platform(get("platform")) or default_platform,  # type: ignore[arg-type]
                impressions=_parse_int(get("impressions")),
                clicks=_parse_int(get("clicks")),
                conversions=_parse_int(get("conversions")),
                spend_micros=_parse_money_micros(get("spend")),
                conversion_value_micros=_parse_money_micros(
                    get("conversion_value")
                ),
                currency=currency,
            )

            # Sanity: clicks can't exceed impressions; if so, treat as
            # a data-quality problem rather than silently accepting.
            if row.clicks > row.impressions and row.impressions > 0:
                raise ValueError(
                    f"clicks ({row.clicks}) > impressions ({row.impressions})"
                )

            accepted.append(row)

            currency_seen = currency_seen or row.currency
            date_min = row.event_date if date_min is None else min(date_min, row.event_date)
            date_max = row.event_date if date_max is None else max(date_max, row.event_date)

        except Exception as exc:
            errors.append(
                CsvParseError(
                    row_number=row_number,
                    raw=raw_dict,
                    error=str(exc),
                )
            )

    date_range = (date_min, date_max) if date_min and date_max else None
    return ParseResult(
        accepted=accepted,
        errors=errors,
        currency=currency_seen,
        date_range=date_range,
    )
