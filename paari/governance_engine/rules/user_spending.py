"""Rule: USER_SPENDING_LIMIT — amount must be within the user's max_transaction_amount."""

from __future__ import annotations

from paari.governance_engine.context import GovernanceContext
from paari.schemas.governance import CheckResult


def check(context: GovernanceContext) -> CheckResult:
    if context.user_policy is None:
        return CheckResult(check="USER_SPENDING_LIMIT", status="FAIL", reason_code="LIMIT_EXCEEDED", details={"missing": "user_policy"})
    if context.transaction is None:
        return CheckResult(check="USER_SPENDING_LIMIT", status="FAIL", reason_code="LIMIT_EXCEEDED", details={"missing": "transaction"})
    amount = context.transaction.amount_paise
    limit = context.user_policy.max_transaction_amount
    if amount > limit:
        return CheckResult(
            check="USER_SPENDING_LIMIT",
            status="FAIL",
            reason_code="LIMIT_EXCEEDED",
            details={"amount": amount, "limit": limit},
        )
    return CheckResult(
        check="USER_SPENDING_LIMIT",
        status="PASS",
        reason_code="WITHIN_LIMIT",
        details={"amount": amount, "limit": limit},
    )
