"""Rule: PAYMENT_CAPABILITY — capability must exist, match tx, cover amount, and be unused."""

from __future__ import annotations

from paari.governance_engine.context import GovernanceContext
from paari.schemas.governance import CheckResult


def check(context: GovernanceContext) -> CheckResult:
    if context.capability is None:
        return CheckResult(check="PAYMENT_CAPABILITY", status="FAIL", reason_code="CAPABILITY_NOT_FOUND", details={})
    if context.transaction and context.capability.transaction_id != context.transaction.id:
        return CheckResult(
            check="PAYMENT_CAPABILITY",
            status="FAIL",
            reason_code="WRONG_TRANSACTION",
            details={
                "capability_tx": context.capability.transaction_id,
                "tx_id": context.transaction.id,
            },
        )
    if context.capability.used:
        return CheckResult(
            check="PAYMENT_CAPABILITY",
            status="FAIL",
            reason_code="ALREADY_USED",
            details={"capability_id": context.capability.display_id},
        )
    if context.transaction and context.capability.max_amount < context.transaction.amount_paise:
        return CheckResult(
            check="PAYMENT_CAPABILITY",
            status="FAIL",
            reason_code="CAPABILITY_AMOUNT_EXCEEDED",
            details={
                "tx_amount": context.transaction.amount_paise,
                "capability_max": context.capability.max_amount,
            },
        )
    return CheckResult(
        check="PAYMENT_CAPABILITY",
        status="PASS",
        reason_code="CAPABILITY_VALID",
        details={"capability_id": context.capability.display_id},
    )
