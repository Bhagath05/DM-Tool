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
        # A real managed Redis — production's hard dependency for the worker,
        # job queue and cache.
        redis_url="redis://red-abc123:6379/0",
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


def test_prod_boots_without_clerk_jwt_audience():
    """Standard Clerk session tokens carry no `aud`. Production MUST boot with
    CLERK_JWT_AUDIENCE empty — issuer + signature + expiry are still enforced.
    Setting it (opt-in) enables aud verification (see test_auth_mode.py)."""
    validate_production_secrets(_prod_settings(clerk_jwt_audience=""))


# ---------------------------------------------------------------------
#  Worker fail-closed — validate_worker_secrets()
# ---------------------------------------------------------------------


def _worker_prod_settings(**over) -> Settings:
    """Worker prod settings. The worker checks DATABASE_URL; the shared
    _prod_settings defaults DB to localhost (the API guard doesn't check DB),
    so give the worker a real one unless a test overrides it."""
    over.setdefault(
        "database_url", "postgresql+psycopg://u:p@prod-db.internal:5432/app"
    )
    return _prod_settings(**over)


def test_worker_prod_passes_with_valid_config():
    from aicmo.config import validate_worker_secrets

    validate_worker_secrets(_worker_prod_settings())  # must not raise


def test_worker_prod_requires_integration_token_key():
    from aicmo.config import validate_worker_secrets

    with pytest.raises(SystemExit) as exc:
        validate_worker_secrets(_worker_prod_settings(integration_token_key=""))
    assert "INTEGRATION_TOKEN_KEY" in str(exc.value)


def test_worker_prod_requires_media_signing_secret():
    from aicmo.config import validate_worker_secrets

    with pytest.raises(SystemExit) as exc:
        validate_worker_secrets(_worker_prod_settings(media_signing_secret=""))
    assert "MEDIA_SIGNING_SECRET" in str(exc.value)


def test_worker_prod_requires_redis_url():
    from aicmo.config import validate_worker_secrets

    with pytest.raises(SystemExit) as exc:
        validate_worker_secrets(_worker_prod_settings(redis_url=""))
    assert "REDIS_URL" in str(exc.value)


def test_worker_prod_requires_database_url():
    from aicmo.config import validate_worker_secrets

    with pytest.raises(SystemExit) as exc:
        # localhost DB is rejected in production.
        validate_worker_secrets(
            _worker_prod_settings(
                database_url="postgresql+psycopg://aicmo:aicmo@localhost:5432/aicmo"
            )
        )
    assert "DATABASE_URL" in str(exc.value)


def test_worker_prod_requires_selected_provider_key():
    from aicmo.config import validate_worker_secrets

    # openai default → OPENAI_API_KEY required.
    with pytest.raises(SystemExit) as exc:
        validate_worker_secrets(
            _worker_prod_settings(llm_default_provider="openai", openai_api_key="")
        )
    assert "OPENAI_API_KEY" in str(exc.value)

    # anthropic default → ANTHROPIC_API_KEY required (openai key present is irrelevant).
    with pytest.raises(SystemExit) as exc:
        validate_worker_secrets(
            _worker_prod_settings(
                llm_default_provider="anthropic",
                anthropic_api_key="",
                openai_api_key="sk-real",
            )
        )
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_worker_dev_is_noop():
    from aicmo.config import validate_worker_secrets

    # Non-production → no-op even with everything missing.
    validate_worker_secrets(
        _worker_prod_settings(
            api_env="development",
            integration_token_key="",
            media_signing_secret="",
            redis_url="",
            openai_api_key="",
        )
    )


def test_worker_does_not_require_clerk_secrets():
    from aicmo.config import validate_worker_secrets

    # Worker has no HTTP auth — CLERK_* absence must not block it.
    validate_worker_secrets(
        _worker_prod_settings(
            clerk_secret_key="",
            clerk_jwt_issuer="",
            clerk_jwks_url="",
            clerk_jwt_audience="",
        )
    )


def test_worker_does_not_require_ip_hash_pepper():
    from aicmo.config import validate_worker_secrets

    validate_worker_secrets(_worker_prod_settings(ip_hash_pepper=""))


def test_worker_error_logs_names_not_values():
    """The failure message must name the missing variable but never leak the
    value of any secret it *did* receive."""
    from aicmo.config import validate_worker_secrets

    secret = "super-secret-media-value-DO-NOT-LOG"
    with pytest.raises(SystemExit) as exc:
        # media secret is set (real), redis is missing → error names REDIS_URL
        # and must NOT contain the media secret value.
        validate_worker_secrets(
            _worker_prod_settings(redis_url="", media_signing_secret=secret)
        )
    msg = str(exc.value)
    assert "REDIS_URL" in msg
    assert secret not in msg


def test_dev_is_unaffected():
    # No-op outside production — dev keeps working without the key.
    validate_production_secrets(_prod_settings(api_env="development", integration_token_key=""))


def test_prod_refuses_localhost_redis():
    """P-stab — the exact wild misconfiguration: production with the localhost
    Redis default means a dead queue + no background jobs. Must refuse to boot."""
    with pytest.raises(SystemExit) as exc:
        validate_production_secrets(
            _prod_settings(redis_url="redis://localhost:6379/0")
        )
    assert "REDIS_URL" in str(exc.value)


def test_prod_refuses_empty_redis():
    with pytest.raises(SystemExit) as exc:
        validate_production_secrets(_prod_settings(redis_url=""))
    assert "REDIS_URL" in str(exc.value)


def test_prod_refuses_loopback_ip_redis():
    with pytest.raises(SystemExit) as exc:
        validate_production_secrets(
            _prod_settings(redis_url="redis://127.0.0.1:6379/0")
        )
    assert "REDIS_URL" in str(exc.value)


def test_dev_allows_localhost_redis():
    """Dev/staging keep the localhost default — the guard is production-only."""
    validate_production_secrets(
        _prod_settings(api_env="development", redis_url="redis://localhost:6379/0")
    )
