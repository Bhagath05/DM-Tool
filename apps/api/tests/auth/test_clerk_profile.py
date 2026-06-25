from aicmo.auth.clerk_profile import is_placeholder_email, profile_from_claims


def test_profile_from_claims_extracts_email_and_name() -> None:
    email, name, avatar = profile_from_claims(
        {
            "sub": "user_abc",
            "email": "founder@example.com",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "image_url": "https://img.clerk.com/avatar.png",
        }
    )
    assert email == "founder@example.com"
    assert name == "Ada Lovelace"
    assert avatar == "https://img.clerk.com/avatar.png"


def test_is_placeholder_email() -> None:
    assert is_placeholder_email("dev-user@pending.local")
    assert is_placeholder_email("user_abc@pending.local")
    assert not is_placeholder_email("founder@example.com")
