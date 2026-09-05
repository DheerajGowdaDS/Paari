"""Decision aggregation and policy-result adapter."""

from __future__ import annotations

from typing import Any

from paari.policy_engine.engine import PolicyEngine, PolicyContext
from paari.policy_engine.operators import evaluate, _resolve, _MISSING  # noqa: F401
from paari.schemas.governance import CheckResult, GovernanceDecision
from paari.schemas.policy import PolicyDecision


def aggregate(
    checks: list[CheckResult],
    request_id: str,
    transaction: Any,
    policy_version: str = "v1",
) -> GovernanceDecision:
    """Aggregate check results with strict priority: DENY > REVIEW > ALLOW.

    No rule overwrites another. The worst outcome wins.
    """
    tx_display_id = getattr(transaction, "display_id", "") if transaction else ""
    tx_id = getattr(transaction, "id", "") if transaction else ""

    decision = GovernanceDecision(
        request_id=request_id,
        transaction_id=tx_id,
        transaction_display_id=tx_display_id,
        policy_version=policy_version,
        checks=list(checks),
    )

    for c in checks:
        if c.status == "FAIL":
            decision.decision = "DENY"
            return decision

    for c in checks:
        if c.status == "REVIEW":
            decision.decision = "REVIEW"
            return decision

    decision.decision = "ALLOW"
    return decision


def from_policy_result(pd: PolicyDecision) -> CheckResult:
    """Convert a PolicyEngine PolicyDecision into a governance CheckResult."""
    status_map = {
        "ALLOW": "PASS",
        "REVIEW": "REVIEW",
        "DENY": "FAIL",
    }
    return CheckResult(
        check="PAARI_POLICY",
        status=status_map.get(pd.decision, "FAIL"),
        reason_code=pd.reason or f"POLICY_{pd.decision}",
        details={
            "policy_version": pd.policy_version,
            "layer": pd.layer.value if hasattr(pd.layer, "value") else str(pd.layer),
            "contributing_rules": pd.contributing_rules,
        },
    )
