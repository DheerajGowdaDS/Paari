"""Operator vocabulary for policy rules.

This exact subset is Rego-translatable: no lambdas, no Python functions in
policy documents. A rule's `when` clause is a tree of these operators only.
"""

from __future__ import annotations

from typing import Any

from paari.schemas.policy import PolicyOp


def _resolve(field_path: str, context: dict[str, Any]) -> Any:
    """Resolve a dotted path like 'tx.amount_paise' against the context dict."""
    current: Any = context
    for part in field_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


class _Missing:
    """Sentinel for absent fields (distinct from None)."""

    def __bool__(self) -> bool:
        return False


_MISSING = _Missing()


def _to_comparable(value: Any) -> Any:
    return None if isinstance(value, _Missing) else value


def op_eq(field: str, value: Any, context: dict[str, Any]) -> bool:
    return _to_comparable(_resolve(field, context)) == value


def op_ne(field: str, value: Any, context: dict[str, Any]) -> bool:
    return _to_comparable(_resolve(field, context)) != value


def op_gt(field: str, value: Any, context: dict[str, Any]) -> bool:
    resolved = _to_comparable(_resolve(field, context))
    return isinstance(resolved, (int, float)) and not isinstance(resolved, bool) and resolved > value


def op_gte(field: str, value: Any, context: dict[str, Any]) -> bool:
    resolved = _to_comparable(_resolve(field, context))
    return isinstance(resolved, (int, float)) and not isinstance(resolved, bool) and resolved >= value


def op_lt(field: str, value: Any, context: dict[str, Any]) -> bool:
    resolved = _to_comparable(_resolve(field, context))
    return isinstance(resolved, (int, float)) and not isinstance(resolved, bool) and resolved < value


def op_lte(field: str, value: Any, context: dict[str, Any]) -> bool:
    resolved = _to_comparable(_resolve(field, context))
    return isinstance(resolved, (int, float)) and not isinstance(resolved, bool) and resolved <= value


def op_in(field: str, value: Any, context: dict[str, Any]) -> bool:
    resolved = _to_comparable(_resolve(field, context))
    return resolved in value if isinstance(value, (list, set, tuple)) else False


def op_not_in(field: str, value: Any, context: dict[str, Any]) -> bool:
    resolved = _to_comparable(_resolve(field, context))
    return resolved not in value if isinstance(value, (list, set, tuple)) else True


def op_and(conditions: list[dict], value: Any, context: dict[str, Any]) -> bool:
    return all(evaluate(cond, context) for cond in conditions)


def op_or(conditions: list[dict], value: Any, context: dict[str, Any]) -> bool:
    return any(evaluate(cond, context) for cond in conditions)


def op_not(condition: dict, value: Any, context: dict[str, Any]) -> bool:
    return not evaluate(condition, context)


_OPERATORS: dict[PolicyOp, Any] = {
    PolicyOp.EQ: op_eq,
    PolicyOp.NE: op_ne,
    PolicyOp.GT: op_gt,
    PolicyOp.GTE: op_gte,
    PolicyOp.LT: op_lt,
    PolicyOp.LTE: op_lte,
    PolicyOp.IN: op_in,
    PolicyOp.NOT_IN: op_not_in,
    PolicyOp.AND: op_and,
    PolicyOp.OR: op_or,
    PolicyOp.NOT: op_not,
}


def get_operator(op: PolicyOp | str) -> Any:
    """Look up an operator by name (case-insensitive)."""
    if isinstance(op, str):
        op = PolicyOp(op)
    return _OPERATORS[op]


def evaluate(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    """Evaluate a condition tree against a context dict.

    A condition is a dict with exactly one key whose value is the operator's
    argument. E.g. {"field": "tx.amount_paise", "op": "gt", "value": 2000000}
    or {"op": "and", "conditions": [...]}.
    """
    if not isinstance(condition, dict) or not condition:
        return False
    op_key = condition.get("op")
    if op_key is None:
        return False
    operator = get_operator(op_key)
    # The operator's argument is whichever non-'op' key is present.
    if op_key in (PolicyOp.AND.value, PolicyOp.OR.value):
        arg = condition.get("conditions", [])
        return operator(arg, None, context)
    if op_key == PolicyOp.NOT.value:
        arg = condition.get("condition", {})
        return operator(arg, None, context)
    field = condition.get("field", "")
    value = condition.get("value")
    return operator(field, value, context)
