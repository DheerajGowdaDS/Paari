"""Step 2 validation: every schema rejects unknown fields (extra=forbid)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paari.schemas import (
    AgentId,
    AuditEvent,
    CapabilitySet,
    CreateTransaction,
    JwtClaims,
    PaymentRequest,
    PaymentVerification,
    PolicyDocument,
    PolicyRule,
    RuntimeContext,
    ToolCall,
    ToolDefinition,
    ToolResult,
)

SCHEMAS_WITH_EXTRA = [
    AgentId,
    AuditEvent,
    CapabilitySet,
    CreateTransaction,
    JwtClaims,
    PaymentRequest,
    PaymentVerification,
    PolicyDocument,
    PolicyRule,
    RuntimeContext,
    ToolCall,
    ToolDefinition,
    ToolResult,
]


@pytest.mark.parametrize("schema", SCHEMAS_WITH_EXTRA, ids=lambda s: s.__name__)
def test_rejects_unknown_field(schema: type) -> None:
    """extra='forbid' must reject any field not declared in the schema."""
    minimal = _minimal_instance(schema)
    injected = {**minimal, "bypass_policy": True, "skip_validation": True}
    with pytest.raises(ValidationError):
        schema.model_validate(injected)


@pytest.mark.parametrize("schema", SCHEMAS_WITH_EXTRA, ids=lambda s: s.__name__)
def test_accepts_valid_instance(schema: type) -> None:
    """A valid instance must parse without error."""
    instance = _minimal_instance(schema)
    parsed = schema.model_validate(instance)
    assert parsed is not None


def _minimal_instance(schema: type) -> dict:
    """Return a minimal valid dict for each schema (hand-maintained)."""
    if schema is AgentId:
        return {"id": "agent-1", "agent_type": "BUYER"}
    if schema is AuditEvent:
        return {"request_id": "req-1", "action": "request_payment", "decision": "ALLOW"}
    if schema is CapabilitySet:
        return {"agent_id": "agent-1", "capabilities": ["catalog.read"]}
    if schema is CreateTransaction:
        return {"merchant_id": "m-1", "buyer_request": "buy shoes", "amount_paise": 120000}
    if schema is JwtClaims:
        return {
            "sub": "agent-1",
            "agent_type": "BUYER",
            "capabilities": ["catalog.read"],
            "policy_version": "v1",
            "iat": 1725000000,
            "exp": 1725000900,
            "jti": "tok-abc",
        }
    if schema is PaymentRequest:
        return {"quote_id": "q-1", "amount_paise": 120000, "currency": "INR", "payment_method": "razorpay"}
    if schema is PaymentVerification:
        return {"transaction_id": "t-1", "gateway_ref": "r-1", "amount_paise": 120000, "currency": "INR", "signature": "sig"}
    if schema is PolicyDocument:
        return {
            "policy_id": "p-1",
            "layer": "MERCHANT",
            "version": "v1",
            "rules": [],
        }
    if schema is PolicyRule:
        return {"id": "M-01", "when": {"field": "x", "op": "eq", "value": 1}, "decision": "ALLOW", "reason": "ok"}
    if schema is RuntimeContext:
        return {"you_are": {"agent_id": "a-1", "agent_type": "BUYER"}}
    if schema is ToolCall:
        return {"call_id": "c-1", "tool_name": "get_product", "arguments": {}}
    if schema is ToolDefinition:
        return {
            "name": "get_product",
            "description": "lookup",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "required_capability": "catalog.read",
            "risk_level": "LOW",
            "allowed_systems": {"SHOPIFY"},
        }
    if schema is ToolResult:
        return {"call_id": "c-1", "tool_name": "get_product", "status": "OK", "payload": {}}
    raise AssertionError(f"no minimal instance for {schema}")
