"""Rule: AUTONOMOUS_PAYMENT — user must allow autonomous payment; large amounts require human confirmation."""

from __future__ import annotations

from paari.governance_engine.context import GovernanceContext
from paari.schemas.governance import CheckResult


def check(context: GovernanceContext) -> CheckResult:
    if context.user_policy is None:
        return CheckResult(
            check="AUTONOMOUS_PAYMENT",
            status="REVIEW",
            reason_code="HUMAN_CONFIRMATION_REQUIRED",
            details={"missing": "user_policy"},
        )
    if not context.user_policy.autonomous_payment:
        return CheckResult(
            check="AUTONOMOUS_PAYMENT",
            status="REVIEW",
            reason_code="HUMAN_CONFIRMATION_REQUIRED",
            details={"autonomous_payment": 0},
        )
    if context.transaction and context.transaction.amount_paise > context.user_policy.confirmation_threshold:
        return CheckResult(
            check="AUTONOMOUS_PAYMENT",
            status="REVIEW",
            reason_code="HUMAN_CONFIRMATION_REQUIRED",
            details={
                "amount": context.transaction.amount_paise,
                "threshold": context.user_policy.confirmation_threshold,
            },
        )
    return CheckResult(
        check="AUTONOMOUS_PAYMENT",
        status="PASS",
        reason_code="AUTONOMOUS_OK",
        details={"autonomous_payment": 1},
    )
