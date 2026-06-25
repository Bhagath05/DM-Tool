"""Rasterise the poster HTML to a PNG.

Order of preference:
  1. Playwright (if installed) — the right production answer; bundles its
     own Chromium, headless, deterministic.
  2. A system Chrome/Chromium via `--headless --screenshot` — zero extra
     Python deps; used in dev and wherever a browser is already present.
     Path comes from settings.poster_chrome_bin / $POSTER_CHROME_BIN, then
     a list of common locations.

If neither is available we raise `PosterRenderUnavailable`; the router
turns that into a clean 503 so the feature degrades instead of 500-ing.

`html_to_png` is synchronous (subprocess / sync Playwright) — callers in
async code run it via `asyncio.to_thread`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import structlog

from aicmo.modules.poster.schemas import LinkedInCopy, PosterTheme
from aicmo.modules.poster.template import render_html

log = structlog.get_logger()


class PosterRenderUnavailable(RuntimeError):
    """No HTML→PNG backend is available on this host."""


_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)


def _chrome_bin() -> str | None:
    # Explicit override first.
    env = os.environ.get("POSTER_CHROME_BIN")
    try:
        from aicmo.config import get_settings

        env = env or getattr(get_settings(), "poster_chrome_bin", None)
    except Exception:  # pragma: no cover - config may be unimportable in tests
        pass
    candidates = ([env] if env else []) + list(_CHROME_CANDIDATES)
    for c in candidates:
        if not c:
            continue
        if os.path.isabs(c) and os.path.exists(c):
            return c
        found = shutil.which(c)
        if found:
            return found
    return None


def _render_with_chrome(
    html: str, *, width: int, height: int, scale: int, timeout: int
) -> bytes:
    chrome = _chrome_bin()
    if not chrome:
        raise PosterRenderUnavailable("no chrome/chromium binary found")
    with tempfile.TemporaryDirectory(prefix="poster_") as d:
        html_path = Path(d) / "poster.html"
        out_path = Path(d) / "poster.png"
        html_path.write_text(html, encoding="utf-8")
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--disable-dev-shm-usage",
            f"--force-device-scale-factor={scale}",
            "--virtual-time-budget=6000",
            f"--window-size={width},{height}",
            f"--screenshot={out_path}",
            html_path.as_uri(),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout, check=False
        )
        if not out_path.exists():
            raise PosterRenderUnavailable(
                f"chrome screenshot failed (rc={proc.returncode}): "
                f"{proc.stderr.decode('utf-8', 'ignore')[:300]}"
            )
        return out_path.read_bytes()


def _render_with_playwright(
    html: str, *, width: int, height: int, scale: int
) -> bytes | None:
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except Exception:
        return None
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=scale,
        )
        page.set_content(html, wait_until="networkidle")
        png = page.screenshot(type="png")
        browser.close()
        return png


def html_to_png(
    html: str, *, width: int = 1200, height: int = 1200, scale: int = 2, timeout: int = 35
) -> bytes:
    """Render an HTML document to PNG bytes. Raises PosterRenderUnavailable."""
    via_pw = _render_with_playwright(html, width=width, height=height, scale=scale)
    if via_pw is not None:
        return via_pw
    return _render_with_chrome(
        html, width=width, height=height, scale=scale, timeout=timeout
    )


def render_poster(
    copy: LinkedInCopy,
    theme: PosterTheme,
    *,
    hero_data_uri: str | None = None,
    width: int = 1200,
    height: int = 1200,
    scale: int = 2,
) -> bytes:
    """Compose the template for `copy`+`theme` and rasterise it to PNG."""
    doc = render_html(
        copy, theme, hero_data_uri=hero_data_uri, width=width, height=height
    )
    png = html_to_png(doc, width=width, height=height, scale=scale)
    log.info("poster.rendered", width=width, height=height, bytes=len(png))
    return png


def renderer_available() -> bool:
    """True if any rasteriser is usable (for health / capability checks)."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401,PLC0415

        return True
    except Exception:
        return _chrome_bin() is not None
