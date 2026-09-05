"""Policy engine: deterministic ALLOW / REVIEW / DENY evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from paari.policy_engine.compiler import CompiledPolicy, compile_policy
from paari.policy_engine.document import load_policy_documents
from paari.policy_engine.operators import evaluate
from paari.schemas.policy import PolicyDecision, PolicyLayer, PolicyRule


@dataclass
class PolicyContext:
    """The context the policy engine evaluates rules against."""

    tx: dict[str, Any] = field(default_factory=dict)
    agent: dict[str, Any] = field(default_factory=dict)
    merchant: dict[str, Any] = field(default_factory=dict)
    store: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"tx": self.tx, "agent": self.agent, "merchant": self.merchant, "store": self.store}


@dataclass
class PolicyEngine:
    """Evaluates a compiled policy against a context.

    Monotonicity invariant:
      - Iterate layers PAARI -> MERCHANT -> STORE -> TX in order.
      - First DENY short-circuits and wins.
      - A REVIEW is sticky: once set, it stays REVIEW unless a later DENY fires.
      - ALLOW is the default; no rule fired.
    """

    compiled: CompiledPolicy
    policy_version: str

    @classmethod
    def for_merchant(cls, merchant_id: str | None = None) -> PolicyEngine:
        """Build an engine from the layered policy documents."""
        docs = load_policy_documents()
        compiled = compile_policy(
            paari=docs[PolicyLayer.PAARI],
            merchant=docs[PolicyLayer.MERCHANT],
            store=docs[PolicyLayer.STORE],
        )
        return cls(compiled=compiled, policy_version=compiled.version)

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        """Evaluate every rule in order; return the effective decision."""
        ctx = context.as_dict()
        decision: str = "ALLOW"
        contributing: list[str] = []
        triggered_layer: PolicyLayer = PolicyLayer.PAARI

        for layer, rule in self.compiled.rules:
            if evaluate(rule.when, ctx):
                if rule.decision == "DENY":
                    return PolicyDecision(
                        decision="DENY",
                        reason=rule.reason,
                        policy_version=self.policy_version,
                        layer=layer,
                        contributing_rules=contributing + [rule.id],
                    )
                if rule.decision == "REVIEW":
                    decision = "REVIEW"
                    triggered_layer = layer
                    contributing.append(rule.id)
                # ALLOW: no change to decision.

        if decision == "REVIEW":
            return PolicyDecision(
                decision="REVIEW",
                reason="policy_review_required",
                policy_version=self.policy_version,
                layer=triggered_layer,
                contributing_rules=contributing,
            )
        return PolicyDecision(
            decision="ALLOW",
            reason="no_rule_triggered",
            policy_version=self.policy_version,
            layer=PolicyLayer.PAARI,
            contributing_rules=[],
        )

    def filter_relevant(self, tool_name: str) -> list[PolicyRule]:
        """Return rules whose `when` references the tool's resource.

        Used by the context builder to project a minimal policy summary for
        the LLM. A rule is relevant if its condition tree mentions a field
        path that the tool is permitted to touch.
        """
        relevant: list[PolicyRule] = []
        for _layer, rule in self.compiled.rules:
            if _references_tool(rule.when, tool_name):
                relevant.append(rule)
        return relevant


def _references_tool(condition: dict[str, Any], tool_name: str) -> bool:
    """Heuristic: a rule is relevant if it touches tx.* or agent.* fields."""
    keys = _collect_field_paths(condition)
    return any(k.startswith("tx.") or k.startswith("agent.") for k in keys)


def _collect_field_paths(condition: dict[str, Any], acc: set[str] | None = None) -> set[str]:
    acc = acc if acc is not None else set()
    if not isinstance(condition, dict):
        return acc
    if "field" in condition and isinstance(condition["field"], str):
        acc.add(condition["field"])
    for key in ("conditions", "condition"):
        child = condition.get(key)
        if isinstance(child, list):
            for item in child:
                _collect_field_paths(item, acc)
        elif isinstance(child, dict):
            _collect_field_paths(child, acc)
    return acc
