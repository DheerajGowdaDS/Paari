"""Risk engine: rule-based scoring for MVP.

Deterministic rules only (no ML). Scores feed into the gateway: a HIGH score
forces REVIEW regardless of policy. Rules are advisory below the threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class RiskRule:
    name: str
    condition: str  # dotted field path, evaluated against context
    threshold: Any
    op: str  # eq | gt | gte | lt | lte | in
    score: int

    def evaluate(self, context: dict[str, Any]) -> bool:
        from paari.policy_engine.operators import _MISSING, _resolve

        resolved = _resolve(self.condition, context)
        if resolved is _MISSING or resolved is None:
            # Sentinel _Missing is falsy; treat absent as no match.
            return False
        if self.op == "eq":
            return resolved == self.threshold
        if self.op == "gt":
            return isinstance(resolved, (int, float)) and not isinstance(resolved, bool) and resolved > self.threshold
        if self.op == "gte":
            return isinstance(resolved, (int, float)) and not isinstance(resolved, bool) and resolved >= self.threshold
        if self.op == "lt":
            return isinstance(resolved, (int, float)) and not isinstance(resolved, bool) and resolved < self.threshold
        if self.op == "lte":
            return isinstance(resolved, (int, float)) and not isinstance(resolved, bool) and resolved <= self.threshold
        if self.op == "in":
            return resolved in self.threshold if isinstance(self.threshold, (list, set, tuple)) else False
        return False


@dataclass(frozen=True)
class RiskScore:
    score: int
    level: RiskLevel
    triggered_rules: list[str] = field(default_factory=list)

    @property
    def is_high(self) -> bool:
        return self.level == RiskLevel.HIGH


# The 8 rules from the MVP decision (decision 6).
RULES: tuple[RiskRule, ...] = (
    RiskRule("high_frequency", "tx.count_per_minute", 5, "gt", 40),
    RiskRule("rapid_repeat", "tx.seconds_since_last", 60, "lt", 30),
    RiskRule("large_transaction", "tx.amount_paise", None, "gt", 25),  # threshold filled per-eval
    RiskRule("just_below_limit", "tx.amount_paise", None, "gt", 35),
    RiskRule("new_agent_high_value", "agent.age_hours", 24, "lt", 30),
    RiskRule("capability_escalation", "agent.requested_cap_in_history", False, "eq", 20),
    RiskRule("round_amount", "tx.amount_paise", None, "gt", 15),
    RiskRule("unusual_hour", "tx.hour_utc", None, "in", 10),
)

# Thresholds that depend on merchant context (filled at evaluation time).
_MERCHANT_AWARE_RULES: dict[str, str] = {
    "large_transaction": "tx.amount_paise > merchant_avg * 3",
    "just_below_limit": "tx.amount_paise > autonomous_limit * 0.95",
    "round_amount": "tx.amount_paise % 100000 == 0 AND tx.amount_paise > 1000000",
    "unusual_hour": "tx.hour_utc NOT IN merchant_active_hours",
}


class RiskEngine:
    """Evaluates the rule set against a transaction context."""

    def __init__(self, rules: tuple[RiskRule, ...] = RULES) -> None:
        self._rules = rules

    def evaluate(self, context: dict[str, Any]) -> RiskScore:
        triggered: list[str] = []
        total = 0
        for rule in self._rules:
            if rule.name in _MERCHANT_AWARE_RULES:
                if self._evaluate_merchant_aware(rule, context):
                    triggered.append(rule.name)
                    total += rule.score
            elif rule.evaluate(context):
                triggered.append(rule.name)
                total += rule.score
        level = RiskLevel.LOW if total < 30 else RiskLevel.MEDIUM if total < 60 else RiskLevel.HIGH
        return RiskScore(score=total, level=level, triggered_rules=triggered)

    @staticmethod
    def _evaluate_merchant_aware(rule: RiskRule, context: dict[str, Any]) -> bool:
        name = rule.name
        tx = context.get("tx", {})
        merchant = context.get("merchant", {})
        amount = tx.get("amount_paise")
        if amount is None:
            return False
        if name == "large_transaction":
            avg = merchant.get("average_transaction_paise", 0)
            return bool(amount > avg * 3 and avg > 0)
        if name == "just_below_limit":
            limit = merchant.get("autonomous_limit_paise", 0)
            return bool(limit > 0 and amount > limit * 0.95)
        if name == "round_amount":
            return bool(amount % 100000 == 0 and amount > 1000000)
        if name == "unusual_hour":
            active = set(merchant.get("active_hours_utc", []))
            return bool(active and tx.get("hour_utc") not in active)
        return False


# Module-level singleton.
RISK_ENGINE = RiskEngine()
