"""Rule: AMOUNT_POLICY — tx.amount_paise must exactly equal quote.amount_paise."""

from __future__ import annotations

from paari.governance_engine.context import GovernanceContext
from paari.schemas.governance import CheckResult


def check(context: GovernanceContext) -> CheckResult:
    if context.transaction is None or context.quote is None:
        return CheckResult(check="AMOUNT_POLICY", status="FAIL", reason_code="AMOUNT_MISMATCH", details={"missing": "tx or quote"})
    if context.transaction.amount_paise != context.quote.amount_paise:
        return CheckResult(
            check="AMOUNT_POLICY",
            status="FAIL",
            reason_code="AMOUNT_MISMATCH",
            details={
                "tx_amount": context.transaction.amount_paise,
                "quote_amount": context.quote.amount_paise,
            },
        )
    return CheckResult(
        check="AMOUNT_POLICY",
        status="PASS",
        reason_code="AMOUNT_MATCH",
        details={"amount_paise": context.transaction.amount_paise},
    )
