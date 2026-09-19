"""Business Brain — evidence-backed knowledge layer for a brand.

BusinessProfile remains the human-editable Brand Brain summary.
This module stores research jobs, typed evidence, ICP hypotheses, and
Phase 2 competitor / market research intelligence (no CRM company store).
"""

from __future__ import annotations

from aicmo.modules.business_brain.models import (  # noqa: F401
    BrainEvidence,
    BrainIcp,
    BrainIcpEvidence,
    BrainResearchJob,
)
