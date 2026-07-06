"""CSV formula-injection defence — a dangerous leading char is neutralised with
a quote; safe values + our own numbers pass through untouched."""

from __future__ import annotations

from aicmo.security.csv_safety import csv_safe, csv_safe_row


def test_formula_triggers_are_prefixed():
    for bad in ("=HYPERLINK(\"http://x\")", "+1+1", "-2+3", "@SUM(A1)", "\t=1", "\r=1"):
        out = csv_safe(bad)
        assert out.startswith("'"), bad


def test_ordinary_values_untouched():
    for ok in ("jane@acme.com", "Brookie Bar", "hello world", ""):
        assert csv_safe(ok) == ok


def test_numbers_pass_through():
    # our own numeric cells must never be turned into text (would break a
    # legitimate negative number).
    assert csv_safe(-50) == -50
    assert csv_safe(1234.5) == 1234.5
    assert csv_safe(0) == 0


def test_row_helper_guards_only_strings():
    row = ["=cmd", "safe", -5, "+evil", 10.0]
    out = csv_safe_row(row)
    assert out == ["'=cmd", "safe", -5, "'+evil", 10.0]
