"""GovernanceEngine — singleton evaluator.

Runs the RULE_PIPELINE, delegates policy check to PolicyEngine, wraps
RiskEngine, aggregates decisions, writes audit events, and transitions
the transaction state machine.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from paari.audit.logger import get_audit
from paari.governance_engine.context import GovernanceContext, GovernanceLoadError
from paari.governance_engine.decision import aggregate, from_policy_result
from paari.governance_engine.rules import RULE_PIPELINE
from paari.governance_engine.state_machine import (
    DECISION_TO_STATE,
    IllegalTransitionError,
    walk_to,
)
from paari.policy_engine.engine import PolicyEngine, PolicyContext
from paari.schemas.governance import CheckResult, GovernanceDecision

_log = logging.getLogger("paari.governance")


class GovernanceEngine:
    """Transaction-level governance evaluator.

    Delegates to the existing PolicyEngine and RiskEngine (REQ-001/002).
    """

    def __init__(
        self,
        policy_engine: PolicyEngine | None = None,
        risk_engine: Any = None,
        audit: Any = None,
    ) -> None:
        self._policy_engine = policy_engine or PolicyEngine.for_merchant()
        self._risk_engine = risk_engine
        self._audit = audit

    async def evaluate(
        self,
        context: GovernanceContext,
        session: AsyncSession | None = None,
        audit: Any = None,
    ) -> GovernanceDecision:
        """Run all checks, aggregate, write audit, and transition state.

        Args:
            context: The loaded governance context.
            session: Optional async session for state transitions. If None,
                     state transitions are skipped (caller handles them).
        """
        request_id = context.request_id or str(uuid.uuid4())
        policy_version = "v1"
        if context.merchant_policy:
            policy_version = context.merchant_policy.version
        elif context.paari_policy:
            policy_version = context.paari_policy.version

        checks: list[CheckResult] = []

        audit_logger = audit or self._audit or get_audit()

        # Run each rule in pipeline
        for rule_fn in RULE_PIPELINE:
            try:
                result = rule_fn(context)
            except Exception as exc:
                _log.exception("rule %s raised", rule_fn.__name__)
                result = CheckResult(
                    check=rule_fn.__name__.upper(),
                    status="FAIL",
                    reason_code="RULE_ERROR",
                    details={"error": str(exc)},
                )
            checks.append(result)

            # Audit each check result
            merchant_id = context.transaction.merchant_id if context.transaction else None
            agent_id = context.transaction.buyer_agent_id if context.transaction else None
            try:
                await audit_logger.log(
                    request_id=request_id,
                    merchant_id=merchant_id,
                    agent_id=agent_id,
                    action=f"GOVERNANCE_CHECK:{result.check}",
                    decision=result.status,
                    policy_version=policy_version,
                    payload={
                        "check": result.check,
                        "status": result.status,
                        "reason_code": result.reason_code,
                        "details": result.details,
                        "transaction_display_id": context.transaction.display_id
                        if context.transaction
                        else "",
                    },
                )
            except Exception:
                _log.exception("audit write failed for check %s", result.check)

        # Delegate policy check to PolicyEngine
        try:
            policy_ctx = PolicyContext(
                tx=context.to_policy_context().get("tx", {}),
                agent=context.to_policy_context().get("agent", {}),
                merchant=context.to_policy_context().get("merchant", {}),
                store=context.to_policy_context().get("store", {}),
            )
            policy_result = self._policy_engine.evaluate(policy_ctx)
            policy_check = from_policy_result(policy_result)
            checks.append(policy_check)
            try:
                await audit_logger.log(
                    request_id=request_id,
                    merchant_id=context.transaction.merchant_id if context.transaction else None,
                    agent_id=context.transaction.buyer_agent_id if context.transaction else None,
                    action="GOVERNANCE_CHECK:PAARI_POLICY",
                    decision=policy_check.status,
                    policy_version=policy_result.policy_version,
                    payload={
                        "check": "PAARI_POLICY",
                        "status": policy_check.status,
                        "reason_code": policy_check.reason_code,
                        "details": policy_check.details,
                    },
                )
            except Exception:
                _log.exception("audit write failed for PAARI_POLICY check")
        except Exception as exc:
            _log.exception("policy engine delegation failed: %s", exc)
            checks.append(
                CheckResult(
                    check="PAARI_POLICY",
                    status="FAIL",
                    reason_code="POLICY_ENGINE_ERROR",
                    details={"error": str(exc)},
                )
            )

        decision = aggregate(checks, request_id, context.transaction, policy_version=policy_version)

        # Write governance decision audit event
        try:
            await audit_logger.log(
                request_id=request_id,
                merchant_id=context.transaction.merchant_id if context.transaction else None,
                agent_id=context.transaction.buyer_agent_id if context.transaction else None,
                action="GOVERNANCE_DECISION",
                decision=decision.decision,
                policy_version=policy_version,
                payload={
                    "decision": decision.decision,
                    "transaction_display_id": decision.transaction_display_id,
                    "failed_checks": [c.reason_code for c in decision.failed_checks],
                    "review_checks": [c.reason_code for c in decision.review_checks],
                },
            )
        except Exception:
            _log.exception("audit write failed for GOVERNANCE_DECISION")

        # State machine transition (walk via GOVERNANCE_PENDING so a fresh
        # CREATED tx can legally reach AUTHORIZED/DENIED/REVIEW_REQUIRED).
        if context.transaction and session is not None:
            try:
                target = DECISION_TO_STATE.get(decision.decision)
                if target:
                    await walk_to(session, context.transaction.id, target)
            except IllegalTransitionError:
                _log.exception("illegal transition for tx %s", context.transaction.id)
            except Exception:
                _log.exception("state transition failed for tx %s", context.transaction.id)

        return decision


# Module-level singleton.
_GOVERNANCE_ENGINE: GovernanceEngine | None = None


def get_governance_engine() -> GovernanceEngine:
    global _GOVERNANCE_ENGINE
    if _GOVERNANCE_ENGINE is None:
        _GOVERNANCE_ENGINE = GovernanceEngine()
    return _GOVERNANCE_ENGINE
