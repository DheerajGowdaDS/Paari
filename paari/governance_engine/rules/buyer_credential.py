"""Rule: BUYER_CREDENTIAL — layered buyer identity (Option 3, blueprint Step 5/17).

Reference-validation (agent row exists + ACTIVE + capabilities/policies) is the
always-on floor.  A buyer JWT is an escalation layer: above the configured
threshold (or when the flag is on), a missing/invalid credential escalates to
REVIEW (default) or DENY (config).

Behaviour matrix:
  Under threshold, no token         → PASS / CREDENTIAL_OPTIONAL
  Under threshold, valid buyer JWT   → PASS / CREDENTIAL_VALID
  Under threshold, bad/expired JWT  → FAIL / CREDENTIAL_INVALID (always blocks)
  Over threshold, no token, deny=F  → REVIEW / CREDENTIAL_REQUIRED
  Over threshold, no token, deny=T  → FAIL / CREDENTIAL_MISSING
  Over threshold, valid buyer JWT    → PASS / CREDENTIAL_VALID
  Any, buyer token sub ≠ buyer id   → FAIL / CREDENTIAL_MISMATCH
"""

from __future__ import annotations

from paari.authn.jwt_verifier import Identity, TokenVerificationError, verify_token
from paari.config import settings
from paari.governance_engine.context import GovernanceContext
from paari.schemas.governance import CheckResult


def check(context: GovernanceContext) -> CheckResult:
    if context.transaction is None:
        return CheckResult(
            check="BUYER_CREDENTIAL",
            status="REVIEW",
            reason_code="CREDENTIAL_OPTIONAL",
            details={"missing": "transaction"},
        )

    credential_json: str | None = getattr(context.transaction, "buyer_credential_json", None)
    token: str | None = credential_json if credential_json else None

    if token is None and not settings.buyer_credential_required:
        below_threshold = (
            context.transaction.amount_paise < settings.buyer_credential_threshold_paise
        )
        if below_threshold:
            return CheckResult(
                check="BUYER_CREDENTIAL",
                status="PASS",
                reason_code="CREDENTIAL_OPTIONAL",
                details={"threshold_paise": settings.buyer_credential_threshold_paise},
            )

    if token is None:
        at_above_threshold = (
            context.transaction.amount_paise >= settings.buyer_credential_threshold_paise
        )
        if at_above_threshold or settings.buyer_credential_required:
            if settings.buyer_credential_deny_if_missing:
                return CheckResult(
                    check="BUYER_CREDENTIAL",
                    status="FAIL",
                    reason_code="CREDENTIAL_MISSING",
                    details={
                        "threshold_paise": settings.buyer_credential_threshold_paise,
                        "tx_amount_paise": context.transaction.amount_paise,
                    },
                )
            return CheckResult(
                check="BUYER_CREDENTIAL",
                status="REVIEW",
                reason_code="CREDENTIAL_REQUIRED",
                details={
                    "threshold_paise": settings.buyer_credential_threshold_paise,
                    "tx_amount_paise": context.transaction.amount_paise,
                },
            )
        return CheckResult(
            check="BUYER_CREDENTIAL",
            status="PASS",
            reason_code="CREDENTIAL_OPTIONAL",
            details={},
        )

    try:
        identity: Identity = verify_token(token)
    except TokenVerificationError:
        return CheckResult(
            check="BUYER_CREDENTIAL",
            status="FAIL",
            reason_code="CREDENTIAL_INVALID",
            details={"reason": "token verification failed"},
        )

    if identity.agent_type.value != "BUYER":
        return CheckResult(
            check="BUYER_CREDENTIAL",
            status="FAIL",
            reason_code="CREDENTIAL_INVALID",
            details={"reason": "token is not a BUYER credential"},
        )

    if context.agent is not None and identity.agent_id != context.agent.id:
        return CheckResult(
            check="BUYER_CREDENTIAL",
            status="FAIL",
            reason_code="CREDENTIAL_MISMATCH",
            details={
                "token_sub": identity.agent_id,
                "referenced_buyer": context.agent.id,
            },
        )

    return CheckResult(
        check="BUYER_CREDENTIAL",
        status="PASS",
        reason_code="CREDENTIAL_VALID",
        details={"verified_agent_id": identity.agent_id},
    )
