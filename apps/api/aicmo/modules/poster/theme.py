"""Resolve a `PosterTheme` from the chosen palette mood + brand.

Accent colours come from the brand kit when present; otherwise from the
palette mood the model picked for the topic (warm food shot vs. cool tech
scene, etc.). Each palette also carries a deep background tone used by the
layouts that need a solid panel.
"""

from __future__ import annotations

from aicmo.modules.poster.schemas import PosterPalette, PosterTheme

_HEX_OK = set("0123456789abcdefABCDEF")

# palette -> (accent1, accent2, deep-bg)
_PALETTES: dict[str, tuple[str, str, str]] = {
    "warm": ("#f6b352", "#ff8a5b", "#0b0a09"),
    "cool": ("#6ea8ff", "#9b7bff", "#0c1120"),
    "bold": ("#34d399", "#a3e635", "#05070b"),
    "mono": ("#e7ecf3", "#9fb0c4", "#0a0c10"),
}


def _is_hex(c: str | None) -> bool:
    if not c or not c.startswith("#"):
        return False
    body = c[1:]
    return len(body) in (3, 6) and all(ch in _HEX_OK for ch in body)


def _clean_site(url: str | None) -> str:
    if not url:
        return ""
    s = url.strip()
    for p in ("https://", "http://"):
        if s.lower().startswith(p):
            s = s[len(p):]
    return s.rstrip("/")[:48]


def build_theme(
    *,
    palette: PosterPalette = "bold",
    brand_name: str | None = None,
    website: str | None = None,
    color_primary: str | None = None,
    color_accent: str | None = None,
    logo_data_uri: str | None = None,
) -> PosterTheme:
    c1, c2, bg = _PALETTES.get(palette, _PALETTES["bold"])
    if _is_hex(color_primary):
        c1 = color_primary  # type: ignore[assignment]
    if _is_hex(color_accent):
        c2 = color_accent  # type: ignore[assignment]
    t = PosterTheme(bg=bg, c1=c1, c2=c2, c3=c2)
    if brand_name and brand_name.strip():
        t.brand_name = brand_name.strip()[:28]
    t.website = _clean_site(website)
    if logo_data_uri:
        t.logo_data_uri = logo_data_uri
    return t
