"""Rule: QUOTE_VALIDATION — quote must exist, be ACCEPTED, match tx, and not be expired."""

from __future__ import annotations

from datetime import UTC, datetime

from paari.governance_engine.context import GovernanceContext
from paari.schemas.governance import CheckResult


def check(context: GovernanceContext) -> CheckResult:
    if context.quote is None:
        return CheckResult(check="QUOTE_VALIDATION", status="FAIL", reason_code="QUOTE_NOT_FOUND", details={})
    if context.quote.state != "ACCEPTED":
        return CheckResult(
            check="QUOTE_VALIDATION",
            status="FAIL",
            reason_code="QUOTE_NOT_ACCEPTED",
            details={"quote_id": context.quote.id, "state": context.quote.state},
        )
    if context.transaction:
        if context.quote.transaction_id != context.transaction.id:
            return CheckResult(
                check="QUOTE_VALIDATION",
                status="FAIL",
                reason_code="QUOTE_MISMATCH",
                details={"quote_tx": context.quote.transaction_id, "tx_id": context.transaction.id},
            )
        if context.quote.amount_paise != context.transaction.amount_paise:
            return CheckResult(
                check="QUOTE_VALIDATION",
                status="FAIL",
                reason_code="QUOTE_AMOUNT_MISMATCH",
                details={
                    "quote_amount": context.quote.amount_paise,
                    "tx_amount": context.transaction.amount_paise,
                },
            )
    try:
        expires = datetime.fromisoformat(context.quote.expires_at)
        if datetime.now(UTC) > expires:
            return CheckResult(
                check="QUOTE_VALIDATION",
                status="FAIL",
                reason_code="QUOTE_EXPIRED",
                details={"quote_id": context.quote.id, "expires_at": context.quote.expires_at},
            )
    except (ValueError, TypeError):
        pass
    return CheckResult(check="QUOTE_VALIDATION", status="PASS", reason_code="QUOTE_VALID", details={"quote_id": context.quote.id})
