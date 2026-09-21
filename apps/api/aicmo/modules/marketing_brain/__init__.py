"""Marketing Brain — unified read-only brand context for reasoning.

Composes Business Brain evidence (canonical researched knowledge) with
profile, analytics, recommendations, outcomes, and learning insights.
Persists nothing. Future Advisor / Agent runtimes consume
`build_context(...)`; they must not invent facts from empty sections.
"""

from aicmo.modules.marketing_brain.schemas import MarketingBrainContext
from aicmo.modules.marketing_brain.service import (
    build_context,
    context_to_prompt_block,
)

__all__ = [
    "MarketingBrainContext",
    "build_context",
    "context_to_prompt_block",
]
