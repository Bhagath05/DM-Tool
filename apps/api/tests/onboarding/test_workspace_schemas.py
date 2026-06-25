"""Schema validation for the onboarding wizard payload (W1-15).

Pure Pydantic — no DB. Pins the wire contract so a future field rename
or constraint change fails CI loudly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aicmo.modules.orgs.schemas import (
    OnboardingWorkspacePayload,
    OnboardingWorkspaceResult,
)


def _valid_payload(**over):
    base = dict(
        organization_name="Acme Coffee Co.",
        organization_slug="acme-coffee",
        brand_name="Acme Espresso",
        brand_slug="acme-espresso",
        display_name="Jane Doe",
    )
    base.update(over)
    return base


class TestPayloadAccepts:
    def test_minimal_valid_payload(self):
        # display_name is optional.
        p = OnboardingWorkspacePayload(
            organization_name="Acme",
            organization_slug="acme",
            brand_name="Main",
            brand_slug="main",
        )
        assert p.organization_slug == "acme"
        assert p.display_name is None

    def test_full_valid_payload(self):
        p = OnboardingWorkspacePayload(**_valid_payload())
        assert p.display_name == "Jane Doe"

    def test_slug_with_numbers_and_hyphens(self):
        OnboardingWorkspacePayload(
            **_valid_payload(organization_slug="acme-2-coffee", brand_slug="b1")
        )


class TestPayloadRejects:
    @pytest.mark.parametrize(
        "bad_slug",
        [
            "Acme",            # uppercase
            "-acme",           # leading hyphen
            "acme-",           # trailing hyphen
            "ac me",           # space
            "acme!",           # punctuation
            "",                # empty
            "a" * 41,          # too long (>40)
            "acme/coffee",     # slash
        ],
    )
    def test_bad_organization_slug(self, bad_slug):
        with pytest.raises(ValidationError):
            OnboardingWorkspacePayload(**_valid_payload(organization_slug=bad_slug))

    @pytest.mark.parametrize(
        "bad_slug",
        ["Brand", "-b", "b-", "b b", ""],
    )
    def test_bad_brand_slug(self, bad_slug):
        with pytest.raises(ValidationError):
            OnboardingWorkspacePayload(**_valid_payload(brand_slug=bad_slug))

    def test_organization_name_required(self):
        with pytest.raises(ValidationError):
            OnboardingWorkspacePayload(**_valid_payload(organization_name=""))

    def test_brand_name_required(self):
        with pytest.raises(ValidationError):
            OnboardingWorkspacePayload(**_valid_payload(brand_name=""))

    def test_name_length_cap(self):
        with pytest.raises(ValidationError):
            OnboardingWorkspacePayload(
                **_valid_payload(organization_name="a" * 121)
            )


class TestResult:
    def test_result_carries_everything_frontend_needs(self):
        # Smoke: ensure the result schema serialises the fields the FE relies on.
        import uuid

        r = OnboardingWorkspaceResult(
            organization_id=uuid.uuid4(),
            organization_slug="acme",
            organization_name="Acme",
            brand_id=uuid.uuid4(),
            brand_slug="main",
            brand_name="Main",
            member_id=uuid.uuid4(),
            role_slugs=["owner"],
        )
        d = r.model_dump()
        assert d["organization_slug"] == "acme"
        assert d["role_slugs"] == ["owner"]
