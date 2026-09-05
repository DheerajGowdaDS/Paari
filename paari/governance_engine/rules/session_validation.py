"""Rule: PAYMENT_SESSION — session must exist, be ACTIVE, not expired, and cover the tx amount."""

from __future__ import annotations

from datetime import UTC, datetime

from paari.governance_engine.context import GovernanceContext
from paari.schemas.governance import CheckResult


def check(context: GovernanceContext) -> CheckResult:
    if context.session is None:
        return CheckResult(check="PAYMENT_SESSION", status="FAIL", reason_code="SESSION_NOT_FOUND", details={})
    if context.session.status != "ACTIVE":
        return CheckResult(
            check="PAYMENT_SESSION",
            status="FAIL",
            reason_code="SESSION_INACTIVE",
            details={"session_id": context.session.display_id, "status": context.session.status},
        )
    try:
        expires = datetime.fromisoformat(context.session.expires_at)
        if datetime.now(UTC) > expires:
            return CheckResult(
                check="PAYMENT_SESSION",
                status="FAIL",
                reason_code="SESSION_EXPIRED",
                details={"session_id": context.session.display_id, "expires_at": context.session.expires_at},
            )
    except (ValueError, TypeError):
        pass
    if context.transaction and context.transaction.amount_paise > context.session.authorized_amount:
        return CheckResult(
            check="PAYMENT_SESSION",
            status="FAIL",
            reason_code="SESSION_AMOUNT_EXCEEDED",
            details={
                "tx_amount": context.transaction.amount_paise,
                "session_amount": context.session.authorized_amount,
            },
        )
    return CheckResult(
        check="PAYMENT_SESSION",
        status="PASS",
        reason_code="SESSION_VALID",
        details={"session_id": context.session.display_id},
    )
