"""Phase 8 Intelligent Onboarding — website fetch + extraction.

Extraction is pure (no network). The SSRF guards are exercised against
loopback / link-local / private targets, which resolve locally and are
rejected *before* any socket is opened — so these stay hermetic.
"""

from __future__ import annotations

import pytest

from aicmo.modules.discovery.fetcher import (
    DiscoveryFetchError,
    _host_is_public,
    extract_signals,
    fetch_website,
    normalize_url,
)

SAMPLE_HTML = """
<!doctype html>
<html>
<head>
  <title>Bella's Bakery — Fresh Sourdough Daily</title>
  <meta name="description" content="Artisan sourdough baked fresh every morning in Pune.">
  <meta property="og:title" content="Bella's Bakery">
  <meta property="og:site_name" content="Bella's Bakery">
  <meta property="og:description" content="Same-day artisan bread.">
  <meta name="keywords" content="sourdough, bakery, pune">
  <style>.hero { color: #8B4513; background: #F5DEB3; }</style>
  <script>window.dataLayer=[];gtag('js', new Date());</script>
  <script async src="https://www.googletagmanager.com/gtm.js?id=GTM-ABC123"></script>
  <script type="application/ld+json">
    {"@type": "Bakery", "name": "Bella's Bakery"}
  </script>
</head>
<body>
  <nav><a href="/about">About</a><a href="/menu">Menu</a></nav>
  <h1>Fresh Sourdough, Every Morning</h1>
  <h2>Baked at 5am, sold by noon</h2>
  <p>We are a family bakery. Call us on +91 98765 43210 or email hello@bellasbakery.in</p>
  <a href="https://instagram.com/bellasbakery">Instagram</a>
  <a href="https://www.facebook.com/bellasbakery">Facebook</a>
  <script>var secret = "SHOULD_NOT_APPEAR_IN_TEXT";</script>
</body>
</html>
"""


class TestNormalizeUrl:
    def test_adds_https_when_scheme_missing(self) -> None:
        assert normalize_url("bellasbakery.in") == "https://bellasbakery.in"

    def test_keeps_existing_scheme(self) -> None:
        assert normalize_url("http://x.com/a") == "http://x.com/a"

    def test_rejects_empty(self) -> None:
        with pytest.raises(DiscoveryFetchError):
            normalize_url("   ")


class TestExtractSignals:
    def setup_method(self) -> None:
        self.s = extract_signals(SAMPLE_HTML, "https://bellasbakery.in/")

    def test_pulls_title_and_meta(self) -> None:
        assert "Bella's Bakery" in self.s["title"]
        assert "Artisan sourdough" in self.s["meta_description"]
        assert self.s["og_site_name"] == "Bella's Bakery"
        assert "sourdough" in self.s["keywords_meta"]

    def test_pulls_headings(self) -> None:
        assert "Fresh Sourdough, Every Morning" in self.s["headings"]
        assert "Baked at 5am, sold by noon" in self.s["headings"]

    def test_finds_social_links(self) -> None:
        assert self.s["social_links"]["instagram"].startswith("https://instagram.com/")
        assert "facebook" in self.s["social_links"]

    def test_finds_contact_details(self) -> None:
        assert "hello@bellasbakery.in" in self.s["emails"]
        assert any("98765" in p for p in self.s["phones"])

    def test_finds_brand_colors(self) -> None:
        assert "#8B4513" in self.s["brand_colors"]
        assert "#F5DEB3" in self.s["brand_colors"]

    def test_detects_analytics_tags(self) -> None:
        assert "Google Tag Manager" in self.s["analytics_tags"]
        assert "Google Analytics" in self.s["analytics_tags"]

    def test_parses_schema_org(self) -> None:
        assert "Bakery" in self.s["schema_types"]

    def test_collects_internal_pages(self) -> None:
        assert any(p.endswith("/about") for p in self.s["nav_pages"])

    def test_script_and_style_never_leak_into_text(self) -> None:
        assert "SHOULD_NOT_APPEAR_IN_TEXT" not in self.s["text_sample"]
        assert "dataLayer" not in self.s["text_sample"]
        assert "We are a family bakery." in self.s["text_sample"]

    def test_malformed_html_does_not_raise(self) -> None:
        out = extract_signals("<html><title>Hi<p>unclosed", "https://x.com/")
        assert "Hi" in out["title"]


class TestSsrfGuards:
    @pytest.mark.asyncio
    async def test_localhost_is_not_public(self) -> None:
        assert await _host_is_public("localhost") is False

    @pytest.mark.asyncio
    async def test_link_local_metadata_ip_is_not_public(self) -> None:
        # The classic cloud-metadata SSRF target.
        assert await _host_is_public("169.254.169.254") is False

    @pytest.mark.asyncio
    async def test_private_ip_is_not_public(self) -> None:
        assert await _host_is_public("10.0.0.1") is False
        assert await _host_is_public("192.168.1.1") is False

    @pytest.mark.asyncio
    async def test_fetch_rejects_loopback_before_any_request(self) -> None:
        with pytest.raises(DiscoveryFetchError, match="private"):
            await fetch_website("http://127.0.0.1:8000/admin")

    @pytest.mark.asyncio
    async def test_fetch_rejects_metadata_endpoint(self) -> None:
        with pytest.raises(DiscoveryFetchError, match="private"):
            await fetch_website("http://169.254.169.254/latest/meta-data/")

    @pytest.mark.asyncio
    async def test_fetch_rejects_non_http_scheme(self) -> None:
        # normalize_url only prepends https:// when there's no scheme, so an
        # explicit file:// survives to the scheme check.
        with pytest.raises(DiscoveryFetchError):
            await fetch_website("file:///etc/passwd")
