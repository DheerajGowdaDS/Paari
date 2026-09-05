"""Rule: MANDATE — mandate bounds for autonomous charging.

Pass-through when the transaction carries no mandate_id (human-checkout
flows are unaffected). Otherwise validates, in order: exists, active,
autonomous enabled, owner match, merchant allow-list, per-transaction
amount, daily usage, expiry. Amounts above requires_review_above escalate
to REVIEW instead of passing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from paari.governance_engine.context import GovernanceContext
from paari.schemas.governance import CheckResult


def _fail(reason_code: str, details: dict[str, Any]) -> CheckResult:
    return CheckResult(check="MANDATE", status="FAIL", reason_code=reason_code, details=details)


def check(context: GovernanceContext) -> CheckResult:
    if context.transaction is None:
        return CheckResult(
            check="MANDATE",
            status="REVIEW",
            reason_code="MANDATE_OPTIONAL",
            details={"missing": "transaction"},
        )
    mandate_id = context.transaction.mandate_id
    if not mandate_id:
        return CheckResult(
            check="MANDATE",
            status="PASS",
            reason_code="MANDATE_NOT_APPLICABLE",
            details={},
        )
    mandate = context.mandate
    if mandate is None:
        return _fail("MANDATE_MISSING", {"mandate_id": mandate_id})
    if mandate.status != "ACTIVE":
        return _fail(
            "MANDATE_INACTIVE", {"mandate_id": mandate.display_id, "status": mandate.status}
        )
    if not mandate.autonomous_enabled:
        return _fail("MANDATE_AUTONOMOUS_DISABLED", {"mandate_id": mandate.display_id})
    owner_id = context.agent.owner_id if context.agent else None
    if owner_id is None or owner_id != mandate.user_id:
        return _fail(
            "MANDATE_OWNER_MISMATCH",
            {
                "mandate_id": mandate.display_id,
                "mandate_user_id": mandate.user_id,
                "owner_id": owner_id,
            },
        )
    try:
        allowed_merchants = json.loads(mandate.allowed_merchants_json or "[]")
    except Exception:
        allowed_merchants = []
    if allowed_merchants:
        merchant_display = context.merchant.display_id if context.merchant else None
        if (
            context.transaction.merchant_id not in allowed_merchants
            and merchant_display not in allowed_merchants
        ):
            return _fail(
                "MANDATE_MERCHANT_BLOCKED",
                {"mandate_id": mandate.display_id, "merchant_id": context.transaction.merchant_id},
            )
    amount = context.transaction.amount_paise
    if amount > mandate.max_per_transaction:
        return _fail(
            "MANDATE_AMOUNT_EXCEEDED",
            {
                "mandate_id": mandate.display_id,
                "tx_amount_paise": amount,
                "max_per_transaction": mandate.max_per_transaction,
            },
        )
    if mandate.expires_at:
        try:
            expiry = datetime.fromisoformat(str(mandate.expires_at).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if datetime.now(UTC) > expiry:
                return _fail("MANDATE_EXPIRED", {"mandate_id": mandate.display_id})
        except ValueError:
            return _fail("MANDATE_EXPIRY_INVALID", {"mandate_id": mandate.display_id})
    used = mandate.daily_used_paise
    details = {
        "mandate_id": mandate.display_id,
        "mandate_policy": "LOADED",
        "tx_amount_paise": amount,
        "max_per_transaction": mandate.max_per_transaction,
        "daily_limit": mandate.daily_limit,
        "daily_used_paise": used,
        "day": datetime.now(UTC).strftime("%Y-%m-%d"),
    }
    if used + amount > mandate.daily_limit:
        return _fail("MANDATE_DAILY_EXCEEDED", details)
    if mandate.requires_review_above and amount > mandate.requires_review_above:
        return CheckResult(
            check="MANDATE", status="REVIEW", reason_code="MANDATE_REVIEW_REQUIRED", details=details
        )
    return CheckResult(check="MANDATE", status="PASS", reason_code="MANDATE_VALID", details=details)
