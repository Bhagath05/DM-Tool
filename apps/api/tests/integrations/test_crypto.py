"""Phase 10.2a — Fernet wrapper unit tests.

Pins:
  - Round-trip works for any string we'd realistically store.
  - Missing key raises `MissingIntegrationKey` with a helpful message.
  - Garbage key raises `MissingIntegrationKey`.
  - Ciphertext encrypted under key A can't be decrypted under key B
    (InvalidIntegrationToken). This is the property that protects us
    if someone rotates the key without re-encrypting.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from aicmo.config import get_settings
from aicmo.modules.integrations import crypto


def test_round_trip(integration_key: str) -> None:
    secret = "EAACEdEose0cBAxxxxx-an-access-token"
    ct = crypto.encrypt(secret)
    assert isinstance(ct, bytes)
    assert crypto.decrypt(ct) == secret


def test_round_trip_unicode(integration_key: str) -> None:
    # Some providers include non-ASCII in refresh tokens.
    secret = "héllo·🌍·tokenζ"
    assert crypto.decrypt(crypto.encrypt(secret)) == secret


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", "")
    get_settings.cache_clear()
    crypto.reset_for_tests()
    with pytest.raises(crypto.MissingIntegrationKey, match="INTEGRATION_TOKEN_KEY"):
        crypto.encrypt("anything")


def test_garbage_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", "this-is-not-a-fernet-key")
    get_settings.cache_clear()
    crypto.reset_for_tests()
    with pytest.raises(crypto.MissingIntegrationKey, match="valid Fernet"):
        crypto.encrypt("anything")


def test_decrypt_wrong_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ciphertext from key A must NOT decrypt under key B."""
    key_a = Fernet.generate_key().decode("ascii")
    key_b = Fernet.generate_key().decode("ascii")

    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", key_a)
    get_settings.cache_clear()
    crypto.reset_for_tests()
    ct = crypto.encrypt("super-secret")

    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", key_b)
    get_settings.cache_clear()
    crypto.reset_for_tests()
    with pytest.raises(crypto.InvalidIntegrationToken):
        crypto.decrypt(ct)


def test_empty_inputs_rejected(integration_key: str) -> None:
    with pytest.raises(ValueError):
        crypto.encrypt(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        crypto.decrypt(b"")
