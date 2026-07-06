"""CSV formula-injection defence (OWASP).

A spreadsheet app (Excel / Sheets / LibreOffice) EXECUTES any cell whose value
begins with `=`, `+`, `-`, `@`, or a leading tab/CR. Since our CSV exports carry
user-controlled text (lead names/emails/notes, deal titles, rep ids), a value
like `=HYPERLINK("http://evil",...)` or `=cmd|'/c calc'!A1` would run on open.

`csv_safe` neutralises that by prefixing a single quote so the app treats the
value as text — the displayed value is unchanged apart from that quote. Only
str cells are guarded; numbers we generate ourselves pass through untouched
(so legitimate negative numbers are never mangled).
"""

from __future__ import annotations

from typing import Any

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in _DANGEROUS:
        return "'" + value
    return value


def csv_safe_row(row: list[Any]) -> list[Any]:
    return [csv_safe(v) for v in row]
