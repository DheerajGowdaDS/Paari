"""Step 5 validation: operators, monotonicity invariant, engine decisions."""

from __future__ import annotations

from paari.policy_engine.compiler import compile_policy
from paari.policy_engine.document import load_policy_documents
from paari.policy_engine.engine import PolicyContext, PolicyEngine
from paari.policy_engine.operators import evaluate
from paari.schemas.policy import PolicyDocument, PolicyLayer, PolicyRule


def _engine() -> PolicyEngine:
    docs = load_policy_documents()
    # Use an empty PAARI layer so merchant/store rules are isolated in tests.
    empty_paari = PolicyDocument(
        policy_id="paari-empty", layer=PolicyLayer.PAARI, version="v1", rules=[]
    )
    compiled = compile_policy(
        paari=empty_paari,
        merchant=docs[PolicyLayer.MERCHANT],
        store=docs[PolicyLayer.STORE],
    )
    return PolicyEngine(compiled=compiled, policy_version=compiled.version)


# --- operators ---------------------------------------------------------------


def test_operator_eq_and_gt() -> None:
    cond = {"field": "tx.amount_paise", "op": "gt", "value": 2000000}
    assert evaluate(cond, {"tx": {"amount_paise": 2500000}})
    assert not evaluate(cond, {"tx": {"amount_paise": 100000}})


def test_operator_in_and_not_in() -> None:
    cond = {"field": "tx.currency", "op": "in", "value": ["INR", "USD"]}
    assert evaluate(cond, {"tx": {"currency": "INR"}})
    assert not evaluate(cond, {"tx": {"currency": "EUR"}})


def test_operator_and_or_not() -> None:
    cond = {
        "op": "and",
        "conditions": [
            {"field": "tx.amount_paise", "op": "gt", "value": 1000000},
            {"op": "not", "condition": {"field": "tx.international", "op": "eq", "value": True}},
        ],
    }
    assert evaluate(cond, {"tx": {"amount_paise": 1500000, "international": False}})
    assert not evaluate(cond, {"tx": {"amount_paise": 1500000, "international": True}})


def test_missing_field_is_not_gt() -> None:
    cond = {"field": "tx.missing", "op": "gt", "value": 1}
    assert not evaluate(cond, {"tx": {}})


# --- monotonicity invariant --------------------------------------------------


def test_deny_first_wins() -> None:
    """A DENY in an earlier layer must short-circuit before a later REVIEW."""
    docs = load_policy_documents()
    empty_paari = PolicyDocument(
        policy_id="paari-empty", layer=PolicyLayer.PAARI, version="v1", rules=[]
    )
    # Build a custom compiled policy: MERCHANT denies, STORE reviews.
    merchant = PolicyDocument(
        policy_id="m", layer=PolicyLayer.MERCHANT, version="v1",
        rules=[PolicyRule(id="M-D", when={"field": "tx.amount_paise", "op": "gt", "value": 100}, decision="DENY", reason="deny")],
    )
    store = PolicyDocument(
        policy_id="s", layer=PolicyLayer.STORE, version="v1",
        rules=[PolicyRule(id="S-R", when={"field": "tx.amount_paise", "op": "gt", "value": 100}, decision="REVIEW", reason="review")],
    )
    compiled = compile_policy(paari=empty_paari, merchant=merchant, store=store)
    engine = PolicyEngine(compiled=compiled, policy_version=compiled.version)
    decision = engine.evaluate(PolicyContext(tx={"amount_paise": 200}))
    assert decision.decision == "DENY"
    assert "M-D" in decision.contributing_rules


def test_review_is_sticky_until_deny() -> None:
    """A REVIEW in an earlier layer stays REVIEW even if a later layer says ALLOW."""
    docs = load_policy_documents()
    empty_paari = PolicyDocument(
        policy_id="paari-empty", layer=PolicyLayer.PAARI, version="v1", rules=[]
    )
    merchant = PolicyDocument(
        policy_id="m", layer=PolicyLayer.MERCHANT, version="v1",
        rules=[PolicyRule(id="M-R", when={"field": "tx.amount_paise", "op": "gt", "value": 100}, decision="REVIEW", reason="review")],
    )
    store = PolicyDocument(
        policy_id="s", layer=PolicyLayer.STORE, version="v1",
        rules=[PolicyRule(id="S-A", when={"field": "tx.amount_paise", "op": "gt", "value": 100}, decision="ALLOW", reason="allow")],
    )
    compiled = compile_policy(paari=empty_paari, merchant=merchant, store=store)
    engine = PolicyEngine(compiled=compiled, policy_version=compiled.version)
    decision = engine.evaluate(PolicyContext(tx={"amount_paise": 200}))
    assert decision.decision == "REVIEW"


def test_empty_policy_allows() -> None:
    docs = load_policy_documents()
    # No rules fire for a small transaction -> ALLOW.
    engine = _engine()
    decision = engine.evaluate(PolicyContext(tx={"amount_paise": 1000, "discount_pct": 0, "quantity": 1, "international": False}))
    assert decision.decision == "ALLOW"


def test_merchant_review_rule_fires() -> None:
    """The seeded merchant policy must REVIEW above ₹20,000."""
    engine = _engine()
    decision = engine.evaluate(PolicyContext(tx={"amount_paise": 2500000, "discount_pct": 0, "quantity": 1, "international": False}))
    assert decision.decision == "REVIEW"
    assert "M-01" in decision.contributing_rules


def test_merchant_deny_rule_fires() -> None:
    engine = _engine()
    decision = engine.evaluate(PolicyContext(tx={"amount_paise": 1000, "discount_pct": 20, "quantity": 1, "international": False}))
    assert decision.decision == "DENY"
    assert "M-02" in decision.contributing_rules
