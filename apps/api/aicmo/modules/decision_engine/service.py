"""Decision Engine service — gather real signals, reason, return decisions.

`decide_from_signals` is the pure, testable core (signals → LLM → report).
`decide` is the thin glue that gathers the (brand-scoped) signals first.
Nothing is persisted; nothing is executed.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.decision_engine import prompts
from aicmo.modules.decision_engine.schemas import (
    DecisionReport,
    DecisionReportResponse,
    DecisionSignals,
)
from aicmo.modules.decision_engine.signals import gather_signals
from aicmo.tenancy.context import TenantContext


async def decide_from_signals(signals: DecisionSignals) -> DecisionReport:
    """Pure of the DB — unit-testable with a mocked LLM router."""
    router = get_llm_router()
    result = await router.generate(
        response_schema=DecisionReport,
        system=prompts.SYSTEM_PROMPT,
        messages=[
            LLMMessage(role="user", content=prompts.build_decision_prompt(signals)),
        ],
        max_tokens=3072,
    )
    return result.data


async def decide(
    session: AsyncSession, *, tenant: TenantContext
) -> DecisionReportResponse:
    signals = await gather_signals(session, tenant=tenant)
    report = await decide_from_signals(signals)
    return DecisionReportResponse(report=report, signals=signals)
