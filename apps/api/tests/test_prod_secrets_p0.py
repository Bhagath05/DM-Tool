"""P0-2 enforcement — production refuses to boot without the token key.

Guarantees that OAuth tokens are always encrypted in production by making
`INTEGRATION_TOKEN_KEY` a required production secret.
"""

from __future__ import annotations

import pytest

from aicmo.config import Settings, validate_production_secrets


def _prod_settings(**over) -> Settings:
    base = dict(
        api_env="production",
        auth_mode="clerk",
        clerk_secret_key="sk_live_real",
        clerk_jwt_issuer="https://x.clerk.test",
        clerk_jwks_url="https://x.clerk.test/.well-known/jwks.json",
        clerk_jwt_audience="aud",
        ip_hash_pepper="a-real-pepper",
        media_signing_secret="a-real-media-secret",
        sentry_dsn="https://abc@o1.ingest.sentry.io/1",
        openai_api_key="sk-real",
        llm_default_provider="openai",
        integration_token_key="a-real-fernet-key-44chars-xxxxxxxxxxxxxxxxxx=",
    )
    base.update(over)
    return Settings(**base)


def test_prod_requires_integration_token_key():
    with pytest.raises(SystemExit) as exc:
        validate_production_secrets(_prod_settings(integration_token_key=""))
    assert "INTEGRATION_TOKEN_KEY" in str(exc.value)


def test_prod_passes_with_all_secrets():
    # Should not raise when every required secret (incl. the token key) is set.
    validate_production_secrets(_prod_settings())


def test_dev_is_unaffected():
    # No-op outside production — dev keeps working without the key.
    validate_production_secrets(_prod_settings(api_env="development", integration_token_key=""))
