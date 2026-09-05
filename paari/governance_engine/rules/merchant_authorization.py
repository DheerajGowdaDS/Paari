"""Rule: MERCHANT_AUTHORIZATION — merchant must exist, be ACTIVE, and have agent_transactions_enabled."""

from __future__ import annotations

from paari.governance_engine.context import GovernanceContext
from paari.schemas.governance import CheckResult


def check(context: GovernanceContext) -> CheckResult:
    if context.merchant is None:
        return CheckResult(check="MERCHANT_AUTHORIZATION", status="FAIL", reason_code="MERCHANT_NOT_FOUND", details={})
    if context.merchant.status != "AI_TRANSACTABLE":
        return CheckResult(
            check="MERCHANT_AUTHORIZATION",
            status="FAIL",
            reason_code="MERCHANT_INACTIVE",
            details={"merchant_id": context.merchant.display_id, "status": context.merchant.status},
        )
    if not context.merchant.agent_transactions_enabled:
        return CheckResult(
            check="MERCHANT_AUTHORIZATION",
            status="FAIL",
            reason_code="MERCHANT_AGENT_TXN_DISABLED",
            details={"merchant_id": context.merchant.display_id},
        )
    return CheckResult(check="MERCHANT_AUTHORIZATION", status="PASS", reason_code="MERCHANT_AUTHORIZED", details={"merchant_id": context.merchant.display_id})
