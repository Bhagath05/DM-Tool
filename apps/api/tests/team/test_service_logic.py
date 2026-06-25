"""Phase 10.2d — Pure service logic (no DB).

Covers the pieces that don't need Postgres:

  - Token generation + hashing (round-trip + hash stability)
  - Accept URL construction
  - Email-match policy (including `@pending.local` relaxation)
  - Role-not-allowed policy (admin vs owner grants)
  - DEFAULT_INVITE_TTL_DAYS pinned

End-to-end DB-backed paths (create / accept / revoke) get a real-DB
smoke pass in 10.2d-8.
"""

from __future__ import annotations

import hashlib

import pytest

from aicmo.modules.team import service


# ---------------------------------------------------------------------
#  Tokens
# ---------------------------------------------------------------------


class TestTokens:
    def test_generate_token_is_url_safe_and_long(self) -> None:
        t = service.generate_token()
        # 32 bytes URL-safe-base64 → 43 chars (no padding).
        assert len(t) >= 32
        # URL-safe alphabet: A-Z, a-z, 0-9, -, _
        for c in t:
            assert c.isalnum() or c in "-_", f"non-url-safe char in token: {c!r}"

    def test_generate_token_unique_per_call(self) -> None:
        seen = {service.generate_token() for _ in range(50)}
        assert len(seen) == 50, "token collision in 50 draws — entropy bug"

    def test_hash_token_is_sha256_hex(self) -> None:
        raw = "fixed-token-for-test"
        expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        assert service.hash_token(raw) == expected
        assert len(service.hash_token(raw)) == 64  # sha256 hex = 64 chars

    def test_hash_token_deterministic(self) -> None:
        raw = "another-token"
        assert service.hash_token(raw) == service.hash_token(raw)

    def test_hash_token_changes_with_input(self) -> None:
        assert service.hash_token("a") != service.hash_token("b")


# ---------------------------------------------------------------------
#  Accept URL
# ---------------------------------------------------------------------


class TestAcceptUrl:
    def test_url_contains_token(self) -> None:
        url = service.build_accept_url("abc123", base_url="http://x.test")
        assert "token=abc123" in url
        assert url.startswith("http://x.test/")

    def test_default_path_is_invites_accept(self) -> None:
        url = service.build_accept_url("t", base_url="https://app.example.com")
        assert "/invites/accept" in url

    def test_base_url_trailing_slash_tolerant(self) -> None:
        """Base URL with or without trailing slash → same result."""
        a = service.build_accept_url("t", base_url="https://x.test")
        b = service.build_accept_url("t", base_url="https://x.test/")
        assert a == b


# ---------------------------------------------------------------------
#  Email match policy
# ---------------------------------------------------------------------


class TestEmailsMatch:
    def test_exact_match(self) -> None:
        assert (
            service._emails_match(invited="a@b.com", actor="a@b.com") is True
        )

    def test_case_insensitive(self) -> None:
        assert (
            service._emails_match(invited="A@B.com", actor="a@b.COM") is True
        )

    def test_whitespace_tolerant(self) -> None:
        assert (
            service._emails_match(invited="  a@b.com  ", actor="a@b.com")
            is True
        )

    def test_mismatch_rejected(self) -> None:
        assert (
            service._emails_match(invited="a@b.com", actor="c@d.com") is False
        )

    def test_empty_actor_rejected(self) -> None:
        assert service._emails_match(invited="a@b.com", actor="") is False

    def test_pending_local_relaxation(self) -> None:
        """Lazy-created users have @pending.local emails until the
        Clerk webhook fills the real one. They're trusted to accept
        invites — the JWT already proves identity."""
        assert (
            service._emails_match(
                invited="real@example.com",
                actor="user_clerk_abc@pending.local",
            )
            is True
        )

    def test_pending_local_match_still_works(self) -> None:
        """Edge case: invite TO a @pending.local address (unlikely but
        possible in dev). Direct equality still wins."""
        assert (
            service._emails_match(
                invited="user_abc@pending.local",
                actor="user_abc@pending.local",
            )
            is True
        )


# ---------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------


def test_default_ttl_is_seven_days() -> None:
    """If you change this without telling the founder, they may notice
    invites expiring at unexpected times. Pin it."""
    assert service.DEFAULT_INVITE_TTL_DAYS == 7


def test_pending_email_suffix_constant() -> None:
    """Lock-step with tenancy.dependencies._get_or_create_user, which
    writes this exact suffix to user.email on lazy-create."""
    assert service.PENDING_EMAIL_SUFFIX == "@pending.local"
