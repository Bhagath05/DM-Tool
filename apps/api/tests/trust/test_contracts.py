"""Contract hygiene: no smuggled fields; the pure scope helper."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aicmo.modules.trust.contracts import (
    CandidateClaim,
    EvidenceRef,
    TrustInput,
    scopes_comparable,
)


class TestExtraForbid:
    def test_trust_input_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            TrustInput(authority="admin")  # type: ignore[call-arg]

    def test_claim_rejects_session_like_fields(self) -> None:
        with pytest.raises(ValidationError):
            CandidateClaim(statement="x", session="db")  # type: ignore[call-arg]

    def test_evidence_ref_rejects_raw_row_payload(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceRef(evidence_id="e1", row={"secret": 1})  # type: ignore[call-arg]


class TestScopesComparable:
    def test_same_single_dimension_is_comparable(self) -> None:
        assert scopes_comparable({"channel": "facebook"}, {"channel": "facebook"})

    def test_case_and_whitespace_insensitive(self) -> None:
        assert scopes_comparable({"channel": " Facebook "}, {"channel": "facebook"})

    def test_different_value_not_comparable(self) -> None:
        assert not scopes_comparable({"channel": "facebook"}, {"channel": "instagram"})

    def test_no_shared_dimension_not_comparable(self) -> None:
        assert not scopes_comparable({"channel": "facebook"}, {"segment": "smb"})

    def test_all_shared_dimensions_must_agree(self) -> None:
        a = {"channel": "facebook", "segment": "smb"}
        assert scopes_comparable(a, {"channel": "facebook", "segment": "smb"})
        assert not scopes_comparable(a, {"channel": "facebook", "segment": "enterprise"})

    def test_non_dict_is_not_comparable(self) -> None:
        assert not scopes_comparable("x", {"channel": "facebook"})  # type: ignore[arg-type]
