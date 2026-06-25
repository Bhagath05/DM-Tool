"""Get-by-name registry for social providers."""

from __future__ import annotations

from functools import lru_cache

from aicmo.providers.social.base import SocialProvider


@lru_cache
def get_social_provider(name: str) -> SocialProvider:
    if name == "instagram":
        from aicmo.providers.social.instagram import InstagramProvider

        return InstagramProvider()
    raise ValueError(f"Unknown social provider: {name}")
