"""Integrations test fixtures.

The integration module's pure-function layers (crypto, state, registry,
oauth_state, provider stubs) are unit-tested without a DB harness. The
service + router layers need:
  - A valid INTEGRATION_TOKEN_KEY so crypto.encrypt/decrypt work.
  - A registry that's been re-seeded between tests if we mutate it.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from aicmo.modules.integrations import crypto


@pytest.fixture
def integration_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Provision a real Fernet key for the test process. Each test
    gets its own key — tests that need to assert "tokens encrypted
    under key A can't be decrypted under key B" use this fixture
    twice."""
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", key)
    # Clear caches so the new key is picked up.
    from aicmo.config import get_settings

    get_settings.cache_clear()
    crypto.reset_for_tests()
    yield key
    crypto.reset_for_tests()
