"""Rule: RISK_CHECK — wraps the existing RiskEngine.

Risk is probabilistic, so it can only escalate to REVIEW — a human decides.
Hard DENY comes from deterministic policy checks only.

Maps RiskLevel:
  LOW    -> PASS   / RISK_ACCEPTABLE
  MEDIUM -> REVIEW / RISK_ELEVATED
  HIGH   -> REVIEW / RISK_ESCALATION
"""

from __future__ import annotations

from paari.governance_engine.context import GovernanceContext
from paari.risk.engine import RiskEngine, RiskLevel
from paari.schemas.governance import CheckResult

_RISK_ENGINE = RiskEngine()


def check(context: GovernanceContext) -> CheckResult:
    risk_ctx = context.to_risk_context()
    score = _RISK_ENGINE.evaluate(risk_ctx)
    level = score.level.value
    if level == RiskLevel.LOW.value:
        return CheckResult(
            check="RISK_CHECK",
            status="PASS",
            reason_code="RISK_ACCEPTABLE",
            details={"score": score.score, "level": level, "triggered_rules": score.triggered_rules},
        )
    if level == RiskLevel.MEDIUM.value:
        return CheckResult(
            check="RISK_CHECK",
            status="REVIEW",
            reason_code="RISK_ELEVATED",
            details={"score": score.score, "level": level, "triggered_rules": score.triggered_rules},
        )
    return CheckResult(
        check="RISK_CHECK",
        status="REVIEW",
        reason_code="RISK_ESCALATION",
        details={"score": score.score, "level": level, "triggered_rules": score.triggered_rules},
    )
