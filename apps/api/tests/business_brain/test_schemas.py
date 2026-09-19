"""Schema / contract smoke for Business Brain responses."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from aicmo.modules.business_brain.schemas import (
    BrainSummaryResponse,
    EvidenceItem,
    IcpGenerateResponse,
    ResearchJobResponse,
)


def test_research_job_response_statuses() -> None:
    now = datetime.now(UTC)
    for status in ("queued", "running", "completed", "partial", "failed"):
        ResearchJobResponse(
            id=uuid.uuid4(),
            kind="website",
            input_url="https://x.example",
            normalized_url="https://x.example",
            status=status,  # type: ignore[arg-type]
            created_at=now,
            updated_at=now,
        )


def test_evidence_item_kinds() -> None:
    now = datetime.now(UTC)
    for kind in ("fact", "observation", "hypothesis", "recommendation"):
        EvidenceItem(
            id=uuid.uuid4(),
            kind=kind,  # type: ignore[arg-type]
            category="business",
            claim="Example claim text for contract.",
            confidence=50,
            status="active",
            source_type="website",
            discovered_at=now,
            created_at=now,
        )


def test_summary_and_icp_contracts() -> None:
    BrainSummaryResponse(
        profile_present=False,
        known=[],
        unknown=["website"],
        evidence_counts={"fact": 0, "observation": 0, "hypothesis": 0, "recommendation": 0},
        icp_count=0,
    )
    IcpGenerateResponse(
        items=[],
        status="INSUFFICIENT_EVIDENCE",
        message="Need evidence first.",
    )
