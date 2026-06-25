"""P0-2 — social OAuth token encryption at rest."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from aicmo.config import get_settings
from aicmo.modules.integrations import crypto
from aicmo.modules.social import token_crypto as tc


@pytest.fixture
def with_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", key)
    get_settings.cache_clear()
    crypto.reset_for_tests()
    yield key
    get_settings.cache_clear()
    crypto.reset_for_tests()


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", "")
    get_settings.cache_clear()
    crypto.reset_for_tests()
    yield
    get_settings.cache_clear()
    crypto.reset_for_tests()


def test_seal_then_unseal_roundtrips(with_key):
    plain = "ya29.super-secret-access-token"
    sealed = tc.seal(plain)
    assert sealed != plain
    assert tc.looks_encrypted(sealed)
    assert tc.unseal(sealed) == plain


def test_seal_is_idempotent(with_key):
    once = tc.seal("token")
    twice = tc.seal(once)  # sealing ciphertext must not double-encrypt
    assert once == twice
    assert tc.unseal(twice) == "token"


def test_unseal_passes_through_legacy_plaintext(with_key):
    # A row written before encryption rollout is plaintext, not Fernet.
    assert tc.unseal("legacy-plaintext-token") == "legacy-plaintext-token"


def test_none_is_preserved(with_key):
    assert tc.seal(None) is None
    assert tc.unseal(None) is None


def test_dev_without_key_stores_plaintext_but_reads_back(no_key):
    # Dev fallback: no key → store plaintext (loud warning), read unchanged.
    assert tc.seal("token") == "token"
    assert tc.unseal("token") == "token"


def test_wrong_key_does_not_crash_read(monkeypatch):
    # Sealed with key A, read with key B → returns None (prompt reconnect),
    # never raises into the publish/sync path.
    k1 = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", k1)
    get_settings.cache_clear()
    crypto.reset_for_tests()
    sealed = tc.seal("token")

    k2 = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_TOKEN_KEY", k2)
    get_settings.cache_clear()
    crypto.reset_for_tests()
    assert tc.unseal(sealed) is None
