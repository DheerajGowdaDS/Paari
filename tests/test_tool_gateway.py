"""Step 11 validation: tool gateway pipeline and all short-circuit paths."""

from __future__ import annotations

from paari.authn.jwt_verifier import Identity
from paari.authz.grants import default_authz
from paari.memory.runtime_state import new_id
from paari.policy_engine.engine import PolicyEngine
from paari.risk.engine import RiskEngine
from paari.schemas.identity import AgentType
from paari.schemas.tool import ToolResultStatus
from paari.tools.gateway import GatewayContext, ToolGateway
from paari.tools.registry import REGISTRY


class _FakeAudit:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log(self, **kwargs) -> str:
        self.events.append(kwargs)
        return kwargs.get("request_id", "evt")


def _buyer_identity() -> Identity:
    return Identity(
        agent_id="buyer-agent-001",
        agent_type=AgentType.BUYER,
        merchant_scope=None,
        capabilities=["catalog.read", "inventory.read", "product.read", "quote.create", "deal.negotiate", "payment.request"],
        policy_version="v1",
        jti="t1",
    )


def _gateway() -> tuple[ToolGateway, _FakeAudit]:
    audit = _FakeAudit()
    gw = ToolGateway(
        registry=REGISTRY,
        authz=default_authz(),
        policy=PolicyEngine.for_merchant(),
        risk=RiskEngine(),
        audit=audit,
    )
    return gw, audit


def _ctx(identity: Identity, **tx_overrides) -> GatewayContext:
    tx = {
        "amount_paise": 1000,
        "discount_pct": 0,
        "quantity": 1,
        "international": False,
        "hour_utc": 12,
        "count_per_minute": 1,
        "seconds_since_last": 600,
    }
    tx.update(tx_overrides)
    return GatewayContext(
        identity=identity,
        merchant_id="merchant-demo-001",
        request_id=new_id(),
        tx_context=tx,
        merchant_context={
            "average_transaction_paise": 120000,
            "autonomous_limit_paise": 2000000,
            "active_hours_utc": [9, 10, 11, 12, 13, 14, 15, 16, 17],
        },
    )


async def test_unknown_tool_returns_error_and_audits() -> None:
    gw, audit = _gateway()
    result = await gw.execute(_ctx(_buyer_identity()), "does_not_exist", {})
    assert result.status == ToolResultStatus.ERROR
    assert result.reason == "unknown_tool"
    assert any(e["action"] == "does_not_exist" and e["decision"] == "FAILED" for e in audit.events)


async def test_unknown_field_rejected_at_schema() -> None:
    """The structural non-bypass defense: bypass_policy cannot exist."""
    gw, audit = _gateway()
    result = await gw.execute(
        _ctx(_buyer_identity()),
        "get_product",
        {"sku": "SKU-001", "bypass_policy": True, "skip_validation": True},
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.reason == "tool_arg_rejected"
    assert any(e["decision"] == "FAILED" and "tool_arg_rejected" in str(e.get("payload")) for e in audit.events)


async def test_missing_capability_denied() -> None:
    """A buyer agent without payment.request cannot call request_payment."""
    gw, audit = _gateway()
    identity = Identity(
        agent_id="buyer-agent-001",
        agent_type=AgentType.BUYER,
        merchant_scope=None,
        capabilities=["catalog.read"],  # no payment.request
        policy_version="v1",
        jti="t2",
    )
    result = await gw.execute(_ctx(identity), "request_payment", {"quote_id": "q-1", "amount_paise": 1000, "currency": "INR", "payment_method": "razorpay"})
    assert result.status == ToolResultStatus.DENIED
    assert result.reason == "missing_capability"
    assert any(e["decision"] == "DENY" and "missing_capability" in str(e.get("payload")) for e in audit.events)


async def test_policy_deny_short_circuits() -> None:
    """A 20% discount is denied by merchant policy M-02."""
    gw, audit = _gateway()
    result = await gw.execute(_ctx(_buyer_identity(), discount_pct=20), "request_quote", {"sku": "SKU-001", "quantity": 1, "discount_pct": 20, "currency": "INR"})
    assert result.status == ToolResultStatus.DENIED
    assert "M-02" in str(result.reason) or "Discount" in result.reason
    assert any(e["decision"] == "DENY" for e in audit.events)


async def test_policy_review_short_circuits() -> None:
    """₹25,000 exceeds the merchant autonomous limit -> REVIEW."""
    gw, audit = _gateway()
    result = await gw.execute(_ctx(_buyer_identity(), amount_paise=2500000), "request_quote", {"sku": "SKU-001", "quantity": 1, "discount_pct": 0, "currency": "INR"})
    assert result.status == ToolResultStatus.REVIEW_REQUIRED
    assert any(e["decision"] == "REVIEW" for e in audit.events)


async def test_risk_high_forces_review() -> None:
    """Burst + large + below-limit + new agent -> risk HIGH -> REVIEW."""
    gw, audit = _gateway()
    result = await gw.execute(
        _ctx(_buyer_identity(), amount_paise=1950000, count_per_minute=6, seconds_since_last=10, hour_utc=3),
        "request_quote",
        {"sku": "SKU-001", "quantity": 1, "discount_pct": 0, "currency": "INR"},
    )
    assert result.status == ToolResultStatus.REVIEW_REQUIRED
    assert "risk_score" in result.reason
    assert any(e["decision"] == "REVIEW" and e.get("risk_score") for e in audit.events)


async def test_happy_path_executes_and_audits() -> None:
    """Low-risk, policy-ALLOW call executes and writes an EXECUTED audit event."""
    gw, audit = _gateway()
    result = await gw.execute(_ctx(_buyer_identity()), "get_product", {"sku": "SKU-001"})
    assert result.status == ToolResultStatus.OK
    assert result.payload["product"]["sku"] == "SKU-001"
    assert any(e["decision"] == "EXECUTED" for e in audit.events)


async def test_policy_allow_is_not_audited_as_allow() -> None:
    """The gateway audits only short-circuits and executions, not ALLOW."""
    gw, audit = _gateway()
    await gw.execute(_ctx(_buyer_identity()), "get_product", {"sku": "SKU-001"})
    # No ALLOW decision should be logged (only EXECUTED).
    assert not any(e["decision"] == "ALLOW" for e in audit.events)
