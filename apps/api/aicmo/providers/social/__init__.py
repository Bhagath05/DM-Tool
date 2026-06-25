"""Social provider abstractions — read-only.

Mirrors `providers/images/` shape. Each provider implements `SocialProvider`,
the registry returns a singleton, and feature code (the service layer)
calls the abstract interface — never the provider SDK directly.
"""

from aicmo.providers.social.base import (
    OAuthCallbackResult,
    OAuthInitResult,
    SocialProvider,
    SyncedAsset,
    SyncResult,
)
from aicmo.providers.social.registry import get_social_provider

__all__ = [
    "OAuthCallbackResult",
    "OAuthInitResult",
    "SocialProvider",
    "SyncedAsset",
    "SyncResult",
    "get_social_provider",
]
