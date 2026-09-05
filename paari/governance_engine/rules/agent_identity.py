"""Rule: AGENT_IDENTITY — agent must exist and be ACTIVE."""

from __future__ import annotations

from paari.governance_engine.context import GovernanceContext
from paari.schemas.governance import CheckResult


def check(context: GovernanceContext) -> CheckResult:
    if context.agent is None:
        return CheckResult(check="AGENT_IDENTITY", status="FAIL", reason_code="AGENT_NOT_FOUND", details={})
    if context.agent.status != "ACTIVE":
        return CheckResult(
            check="AGENT_IDENTITY",
            status="FAIL",
            reason_code="AGENT_INACTIVE",
            details={"agent_id": context.agent.display_id, "status": context.agent.status},
        )
    return CheckResult(check="AGENT_IDENTITY", status="PASS", reason_code="AGENT_ACTIVE", details={"agent_id": context.agent.display_id})
