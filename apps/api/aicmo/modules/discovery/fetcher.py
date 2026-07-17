"""Website fetch + signal extraction for the Intelligent Onboarding
Website Discovery Engine.

Real network fetch — no placeholders. Two responsibilities:

1. `fetch_website(url)` — SSRF-guarded HTTP GET. Rejects non-http(s)
   schemes, private / loopback / link-local / reserved IPs (checked on
   every redirect hop), caps the body size, and times out. Returns the
   final URL + decoded HTML.

2. `extract_signals(html, base_url)` — pulls the marketing-relevant
   signals out of raw HTML using only the standard library (no new
   dependency): title, meta description, Open Graph / Twitter cards,
   schema.org JSON-LD, headings, navigation text, social links, contact
   details, detected analytics tags, brand colours, and a trimmed sample
   of visible copy. The LLM turns these into a Brand Brain draft.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
import structlog

log = structlog.get_logger()

_MAX_BYTES = 2_000_000  # 2 MB is plenty for a homepage; guards memory.
_TIMEOUT = 12.0
_MAX_REDIRECTS = 4
_UA = (
    "Mozilla/5.0 (compatible; DMToolDiscoveryBot/1.0; +https://dm-tool.app/bot)"
)

_SOCIAL_HOSTS = {
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "linkedin.com": "linkedin",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "tiktok.com": "tiktok",
    "pinterest.com": "pinterest",
    "threads.net": "threads",
    "twitter.com": "twitter",
    "x.com": "twitter",
}


class DiscoveryFetchError(Exception):
    """Raised when a URL can't be fetched safely (bad scheme, blocked host,
    timeout, too large, or non-HTML)."""


# ---------------------------------------------------------------------
#  SSRF-safe fetch
# ---------------------------------------------------------------------


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise DiscoveryFetchError("No website URL provided.")
    if not re.match(r"^https?://", raw, re.IGNORECASE):
        raw = f"https://{raw}"
    return raw


async def _host_is_public(host: str) -> bool:
    """Resolve `host` and confirm every address is a public, routable IP.
    Blocks localhost, private ranges, link-local, reserved + cloud-metadata
    addresses (169.254.169.254 is link-local, so it's covered)."""
    if not host:
        return False
    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


async def fetch_website(url: str) -> tuple[str, str]:
    """Fetch a public web page safely. Returns (final_url, html).

    Follows redirects manually so each hop's host is SSRF-validated (a
    common bypass is an allowed URL that 302s to 169.254.169.254)."""
    current = normalize_url(url)
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=_TIMEOUT,
        headers={"User-Agent": _UA, "Accept": "text/html,*/*"},
    ) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            parsed = urlparse(current)
            if parsed.scheme not in ("http", "https"):
                raise DiscoveryFetchError("Only http(s) websites are supported.")
            if not await _host_is_public(parsed.hostname or ""):
                raise DiscoveryFetchError(
                    "That address can't be reached (it points somewhere private)."
                )
            try:
                resp = await client.get(current)
            except httpx.HTTPError as e:
                raise DiscoveryFetchError(
                    "We couldn't open that website. Check the address and try again."
                ) from e

            if resp.is_redirect:
                loc = resp.headers.get("location")
                if not loc:
                    break
                current = urljoin(current, loc)
                continue

            if resp.status_code >= 400:
                raise DiscoveryFetchError(
                    f"The website returned an error ({resp.status_code})."
                )
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                raise DiscoveryFetchError("That link isn't a web page.")
            raw = resp.content[:_MAX_BYTES]
            html = raw.decode(resp.encoding or "utf-8", errors="replace")
            return str(resp.url), html
    raise DiscoveryFetchError("Too many redirects — the website couldn't load.")


# ---------------------------------------------------------------------
#  HTML signal extraction (stdlib only)
# ---------------------------------------------------------------------

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.metas: dict[str, str] = {}
        self.links: list[str] = []
        self.headings: list[str] = []
        self.jsonld: list[str] = []
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._heading_tag: str | None = None
        self._in_jsonld = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = dict(attrs)
        if tag in _SKIP_TAGS:
            if tag == "script" and a.get("type") == "application/ld+json":
                self._in_jsonld = True
            else:
                self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower().strip()
            content = a.get("content")
            if key and content:
                self.metas.setdefault(key, content.strip())
        elif tag in ("a", "link"):
            href = a.get("href")
            if href:
                self.links.append(href.strip())
        elif tag in ("h1", "h2", "h3"):
            self._heading_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if tag == "script" and self._in_jsonld:
                self._in_jsonld = False
            elif self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        elif tag == self._heading_tag:
            self._heading_tag = None

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self.jsonld.append(data)
            return
        if self._skip_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title = (self.title + " " + text).strip()
        elif self._heading_tag:
            self.headings.append(text)
        elif len(self.text_parts) < 400:
            self.text_parts.append(text)


_EMAIL_RX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RX = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_HEX_RX = re.compile(r"#[0-9a-fA-F]{6}\b")


def _detect_analytics(html: str) -> list[str]:
    found = []
    checks = {
        "Google Analytics": r"gtag\(|google-analytics\.com|G-[A-Z0-9]{6,}",
        "Google Tag Manager": r"googletagmanager\.com|GTM-[A-Z0-9]+",
        "Meta Pixel": r"connect\.facebook\.net|fbq\(",
        "LinkedIn Insight": r"snap\.licdn\.com|_linkedin_partner_id",
        "TikTok Pixel": r"analytics\.tiktok\.com|ttq\.",
        "Hotjar": r"static\.hotjar\.com",
    }
    for label, rx in checks.items():
        if re.search(rx, html):
            found.append(label)
    return found


def extract_signals(html: str, base_url: str) -> dict:
    """Turn raw HTML into a compact dict of marketing signals."""
    p = _Extractor()
    try:
        p.feed(html)
        # close() flushes HTMLParser's internal buffer — without it the tail
        # of the document (often the richest copy) is silently dropped.
        p.close()
    except Exception as e:
        log.warning("discovery.parse_failed", error=str(e)[:120])

    # Social + internal links.
    socials: dict[str, str] = {}
    internal_pages: list[str] = []
    base_host = urlparse(base_url).hostname or ""
    for href in p.links:
        full = urljoin(base_url, href)
        host = (urlparse(full).hostname or "").lower().removeprefix("www.")
        for social_host, name in _SOCIAL_HOSTS.items():
            if host == social_host or host.endswith("." + social_host):
                socials.setdefault(name, full)
        if host == base_host.lower().removeprefix("www.") and full not in internal_pages:
            if len(internal_pages) < 40:
                internal_pages.append(full)

    text_blob = " ".join(p.text_parts)
    emails = sorted(set(_EMAIL_RX.findall(html)))[:5]
    phones = sorted({m.strip() for m in _PHONE_RX.findall(text_blob)})[:5]
    colors = _dedupe_keep_order(_HEX_RX.findall(html))[:8]

    # schema.org JSON-LD — best-effort parse of the first valid blob.
    schema_types: list[str] = []
    for blob in p.jsonld[:5]:
        try:
            data = json.loads(blob)
        except Exception:
            continue
        for node in data if isinstance(data, list) else [data]:
            if isinstance(node, dict) and node.get("@type"):
                t = node["@type"]
                schema_types.extend(t if isinstance(t, list) else [t])

    return {
        "final_url": base_url,
        "title": p.title[:300],
        "meta_description": p.metas.get("description", "")[:600],
        "og_title": p.metas.get("og:title", "")[:300],
        "og_description": p.metas.get("og:description", "")[:600],
        "og_site_name": p.metas.get("og:site_name", "")[:120],
        "og_image": p.metas.get("og:image", "")[:500],
        "twitter_title": p.metas.get("twitter:title", "")[:300],
        "keywords_meta": p.metas.get("keywords", "")[:400],
        "headings": _dedupe_keep_order(p.headings)[:25],
        "nav_pages": internal_pages[:25],
        "social_links": socials,
        "emails": emails,
        "phones": phones,
        "brand_colors": colors,
        "schema_types": _dedupe_keep_order(schema_types)[:10],
        "analytics_tags": _detect_analytics(html),
        "text_sample": text_blob[:6000],
    }


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.strip()
        low = key.lower()
        if key and low not in seen:
            seen.add(low)
            out.append(key)
    return out
