"""Phase 3A — belief confidence, schema contract, secret guard, agent isolation.

All run WITHOUT Postgres: pure derivation, schema validation, and structural
guarantees (the agent has no belief-write capability).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from aicmo.modules.belief import service
from aicmo.modules.belief.confidence import derive_confidence, derive_status
from aicmo.modules.belief.enums import BeliefStatus, EvidenceRefKind, EvidenceRelation
from aicmo.modules.belief.schemas import BeliefCreate, EvidenceRefInput


# --- confidence is evidence-derived, never asserted -------------------------
def test_zero_support_is_zero_confidence():
    conf, reason = derive_confidence(supports=0, contradicts=0, experimental=False)
    assert conf == 0 and "unvalidated" in reason.lower()


def test_experimental_evidence_raises_ceiling_over_observational():
    obs, _ = derive_confidence(supports=2, contradicts=0, experimental=False)
    exp, _ = derive_confidence(supports=2, contradicts=0, experimental=True)
    assert exp > obs


def test_contradictions_reduce_confidence():
    clean, _ = derive_confidence(supports=3, contradicts=0, experimental=False)
    conflicted, _ = derive_confidence(supports=3, contradicts=2, experimental=False)
    assert conflicted < clean


def test_confidence_never_reaches_certainty():
    conf, _ = derive_confidence(supports=99, contradicts=0, experimental=True)
    assert conf < 100


def test_status_rules():
    assert derive_status(supports=0, contradicts=0) is BeliefStatus.UNVALIDATED
    assert derive_status(supports=2, contradicts=0) is BeliefStatus.ACTIVE
    assert derive_status(supports=1, contradicts=2) is BeliefStatus.CONTRADICTED


# --- the model/caller cannot assert confidence, status, or tenant -----------
def test_belief_create_rejects_confidence():
    with pytest.raises(ValidationError):
        BeliefCreate.model_validate(
            {"category": "channel", "subject_key": "k", "statement": "s", "confidence": 99}
        )


def test_belief_create_rejects_status_and_tenant_fields():
    for smuggled in ({"status": "active"}, {"brand_id": str(uuid.uuid4())}, {"organization_id": "x"}):
        with pytest.raises(ValidationError):
            BeliefCreate.model_validate(
                {"category": "channel", "subject_key": "k", "statement": "s", **smuggled}
            )


def test_belief_create_valid_minimal():
    b = BeliefCreate.model_validate(
        {"category": "channel", "subject_key": "reels_vs_static", "statement": "Reels engaged more."}
    )
    assert b.evidence == [] and b.scope == {}


def test_evidence_ref_rejects_extra_fields():
    with pytest.raises(ValidationError):
        EvidenceRefInput.model_validate(
            {"ref_kind": "brain_evidence", "ref_id": str(uuid.uuid4()), "tenant_id": "x"}
        )


# --- secret guard -----------------------------------------------------------
@pytest.mark.parametrize(
    "secret",
    [
        "sk-0123456789abcdefghij",
        "AKIA0123456789ABCD",
        "api_key=foobarbaz",
        "SMTP_PASSWORD: hunter2xyz",
        "bearer abcdefghij0123456789klmno",
        "-----BEGIN PRIVATE KEY-----",
    ],
)
def test_secret_guard_rejects_secrets(secret):
    with pytest.raises(service.BeliefValidationError):
        service._assert_safe_text(secret)


@pytest.mark.parametrize(
    "ok",
    [
        "Instagram Reels outperformed static posts for fitness audiences.",
        "Our password reset flow converts well.",
        "The API is documented; users like the onboarding.",
    ],
)
def test_secret_guard_allows_ordinary_prose(ok):
    service._assert_safe_text(ok)  # must not raise


def test_scope_is_bounded_and_secret_free():
    big = {f"k{i}": "v" for i in range(50)}
    out = service._bounded_scope(big)
    assert len(out) <= 12  # key cap
    with pytest.raises(service.BeliefValidationError):
        service._bounded_scope({"leak": "api_key=sk-abcdef0123456789"})


# --- data_source evidence validation (no DB needed) -------------------------
@pytest.mark.asyncio
async def test_data_source_requires_note_and_is_secret_scanned():
    tenant = MagicMock(brand_id=uuid.uuid4())
    # missing note → rejected
    with pytest.raises(service.BeliefValidationError):
        await service._validate_ref_ownership(
            MagicMock(), tenant, EvidenceRefInput(ref_kind=EvidenceRefKind.DATA_SOURCE, note=None)
        )
    # secret in note → rejected
    with pytest.raises(service.BeliefValidationError):
        await service._validate_ref_ownership(
            MagicMock(), tenant,
            EvidenceRefInput(ref_kind=EvidenceRefKind.DATA_SOURCE, note="key=sk-0123456789abcdef"),
        )
    # clean note → ok (no DB touched for data_source)
    await service._validate_ref_ownership(
        MagicMock(), tenant,
        EvidenceRefInput(ref_kind=EvidenceRefKind.DATA_SOURCE, note="Meta Ads export, Q1"),
    )


@pytest.mark.asyncio
async def test_db_backed_ref_requires_ref_id():
    tenant = MagicMock(brand_id=uuid.uuid4())
    with pytest.raises(service.BeliefValidationError):
        await service._validate_ref_ownership(
            MagicMock(), tenant, EvidenceRefInput(ref_kind=EvidenceRefKind.BRAIN_EVIDENCE, ref_id=None)
        )


# --- the LLM/agent has NO belief-write capability ---------------------------
def test_agent_registry_has_no_belief_write_tool():
    from aicmo.agent.tools import get_default_registry

    tools = get_default_registry().list_tools()
    for t in tools:
        assert t["operation_class"] == "read"  # every agent tool is read-only
        assert "belief" not in t["name"] and "memory" not in t["name"]
        assert "write" not in t["name"] and "create" not in t["name"]
    # There is simply no tool through which a model could mutate belief memory.
    assert not any("belief" in t["name"] for t in tools)


def test_relation_enum_values():
    assert EvidenceRelation.SUPPORTS.value == "supports"
    assert EvidenceRelation.CONTRADICTS.value == "contradicts"
