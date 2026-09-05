"""Rule: AGENT_AUTHORIZATION — agent must have payment.request capability."""

from __future__ import annotations

from paari.governance_engine.context import GovernanceContext
from paari.schemas.governance import CheckResult


def check(context: GovernanceContext) -> CheckResult:
    if context.agent is None:
        return CheckResult(
            check="AGENT_AUTHORIZATION", status="FAIL", reason_code="AGENT_NOT_FOUND", details={}
        )
    if "payment.request" in context.agent.capabilities:
        return CheckResult(
            check="AGENT_AUTHORIZATION",
            status="PASS",
            reason_code="CAPABILITY_PRESENT",
            details={"agent_id": context.agent.display_id},
        )
    mandate_id = getattr(context.transaction, "mandate_id", None) if context.transaction else None
    if mandate_id and "payment.mandate_charge" in context.agent.capabilities:
        return CheckResult(
            check="AGENT_AUTHORIZATION",
            status="PASS",
            reason_code="CAPABILITY_PRESENT_MANDATE",
            details={"agent_id": context.agent.display_id, "mandate_id": mandate_id},
        )
    return CheckResult(
        check="AGENT_AUTHORIZATION",
        status="FAIL",
        reason_code="MISSING_CAPABILITY",
        details={
            "agent_id": context.agent.display_id,
            "required": "payment.request",
            "has": context.agent.capabilities,
        },
    )
