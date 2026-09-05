"""End-to-end test: the 10 validation checks from the plan's §20.

Uses respx to mock the LLM API and a fresh in-memory DB where needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import httpx
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from paari.audit.logger import AuditLogger
from paari.authn.jwt_issuer import issue_agent_token
from paari.authn.jwt_verifier import verify_token
from paari.llm.client import LLMClient
from paari.llm.context_builder import CONTEXT_BUILDER
from paari.runtime.loop import RuntimeLoop
from paari.runtime.planner import Planner
from paari.runtime.step_executor import StepExecutor
from paari.schemas.identity import AgentType
from paari.tools.gateway import GATEWAY


def _llm_json(content: str | None, tool_calls: list[dict] | None = None) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": content or "",
                    "tool_calls": [
                        {
                            "id": f"call-{i}",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                        }
                        for i, tc in enumerate(tool_calls or [])
                    ],
                }
            }
        ]
    }


def _identity_with_caps(caps: list[str]):
    """Issue a token with specific capabilities and return the verified identity."""
    token = issue_agent_token(
        agent_id="buyer-agent-001",
        agent_type=AgentType.BUYER,
        capabilities=caps,
        merchant_scope=None,
    )
    return verify_token(token)


def _loop() -> RuntimeLoop:
    return RuntimeLoop(
        llm=LLMClient(base_url="https://api.example.com/v1", api_key="sk-test", model="m"),
        context_builder=CONTEXT_BUILDER,
        gateway=GATEWAY,
        executor=StepExecutor(GATEWAY),
        audit=AuditLogger(),
        planner=Planner(),
    )


# --- Check 1: AuthN — unauthenticated POST /agent/run returns 401 ---
async def test_01_unauthenticated_returns_401():
    from httpx import ASGITransport, AsyncClient

    from paari.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/agent/run", json={"buyer_request": "hi"})
    assert response.status_code == 401
    assert response.json()["detail"] == "missing_authorization"


# --- Check 2: AuthZ — buyer without payment.request is denied ---
@respx.mock
async def test_02_missing_capability_denied():
    identity = _identity_with_caps(["catalog.read"])
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_llm_json("", [{"name": "request_payment", "args": {"quote_id": "q-1", "amount_paise": 1000, "currency": "INR", "payment_method": "razorpay"}}]))
    )
    response = await _loop().run(identity, "pay", amount_paise=1000)
    assert response.status.value == "denied"
    assert "missing_capability" in str(response.tool_results)


# --- Check 3: Policy DENY — 20% discount is denied ---
@respx.mock
async def test_03_policy_deny():
    identity = _identity_with_caps(["catalog.read", "inventory.read", "product.read", "quote.create", "deal.negotiate", "payment.request"])
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_llm_json("", [{"name": "request_quote", "args": {"sku": "SKU-001", "quantity": 1, "discount_pct": 20, "currency": "INR"}}]))
    )
    response = await _loop().run(identity, "buy with 20% off", amount_paise=1000, discount_pct=20)
    assert response.status.value == "denied"


# --- Check 4: Policy REVIEW — ₹25,000 above merchant limit ---
@respx.mock
async def test_04_policy_review():
    identity = _identity_with_caps(["catalog.read", "inventory.read", "product.read", "quote.create", "deal.negotiate", "payment.request"])
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_llm_json("", [{"name": "request_quote", "args": {"sku": "SKU-001", "quantity": 1, "discount_pct": 0, "currency": "INR"}}]))
    )
    response = await _loop().run(identity, "buy big", amount_paise=2500000)
    assert response.status.value == "review_required"


# --- Check 5: Risk REVIEW — burst + large + below-limit + new agent ---
@respx.mock
async def test_05_risk_review():
    identity = _identity_with_caps(["catalog.read", "inventory.read", "product.read", "quote.create", "deal.negotiate", "payment.request"])
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_llm_json("", [{"name": "request_quote", "args": {"sku": "SKU-001", "quantity": 1, "discount_pct": 0, "currency": "INR"}}]))
    )
    response = await _loop().run(
        identity, "buy big",
        amount_paise=1950000, count_per_minute=6, seconds_since_last=10, hour_utc=3,
    )
    assert response.status.value == "review_required"
    assert "risk_score" in response.message or any("risk" in str(r) for r in response.tool_results)


# --- Check 6: Non-bypass — bypass_policy is rejected at the gateway ---
@respx.mock
async def test_06_bypass_policy_rejected():
    identity = _identity_with_caps(["catalog.read", "inventory.read", "product.read", "quote.create", "deal.negotiate", "payment.request"])
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_llm_json("", [{"name": "get_product", "args": {"sku": "SKU-001", "bypass_policy": True, "skip_validation": True}}]))
    )
    response = await _loop().run(identity, "sneaky", amount_paise=1000)
    assert response.status.value == "error"
    assert "tool_arg_rejected" in str(response.tool_results) or "rejected" in response.message.lower()


# --- Check 7: Payment trust — agent cannot claim payment success ---
@respx.mock
async def test_07_payment_not_trusted_from_agent():
    """The LLM saying 'payment done' must not transition payment state."""
    identity = _identity_with_caps(["catalog.read", "inventory.read", "product.read", "quote.create", "deal.negotiate", "payment.request"])
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_llm_json("Payment complete!"))
    )
    response = await _loop().run(identity, "buy", amount_paise=1000)
    # No tool calls; agent's prose claim is not trusted.
    assert response.status.value == "completed"
    assert response.tool_results == []


# --- Check 8: Tenant isolation — second merchant's data does not leak ---
async def test_08_tenant_isolation():
    """Reviews for merchant A are not visible to merchant B."""
    from paari.review.service import ReviewService

    db_path = Path(__file__).resolve().parent / f"_test_e2e_iso_{uuid4().hex}.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    svc = ReviewService(session_maker=maker, sla_hours=4)
    await svc.create(merchant_id="merchant-A", transaction_id="tx-A", triggered_by="POLICY", reason="A's data")
    await svc.create(merchant_id="merchant-B", transaction_id="tx-B", triggered_by="POLICY", reason="B's data")
    a_pending = await svc.list_pending(merchant_id="merchant-A")
    b_pending = await svc.list_pending(merchant_id="merchant-B")
    a_reasons = {r.reason for r in a_pending}
    b_reasons = {r.reason for r in b_pending}
    assert "A's data" in a_reasons and "B's data" not in a_reasons
    assert "B's data" in b_reasons and "A's data" not in b_reasons


# --- Check 9: SLA timeout — review past its SLA auto-denies ---
async def test_09_sla_timeout_auto_denies():
    from paari.review.service import ReviewService

    db_path = Path(__file__).resolve().parent / f"_test_e2e_sla_{uuid4().hex}.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    svc = ReviewService(session_maker=maker, sla_hours=0)
    await svc.create(merchant_id="m", transaction_id="t", triggered_by="POLICY", reason="x")
    # Force the SLA into the past by creating with a negative delta via direct insert.
    async with maker() as session:
        from sqlalchemy import text
        await session.execute(
            text("UPDATE reviews SET sla_expires_at = '2000-01-01 00:00:00' WHERE decision IS NULL")
        )
        await session.commit()
    denied = await svc.auto_deny_expired()
    assert denied >= 1
    pending = await svc.list_pending(merchant_id="m")
    assert pending == []


# --- Check 10: Audit completeness — every EXECUTED tool has a matching audit row ---
@respx.mock
async def test_10_audit_completeness():
    from sqlalchemy import text

    identity = _identity_with_caps(["catalog.read", "inventory.read", "product.read", "quote.create", "deal.negotiate", "payment.request"])
    request_id_marker = f"e2e-marker-{uuid4().hex}"
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_llm_json("", [{"name": "get_product", "args": {"sku": "SKU-001"}}]))
    )
    # Run with a custom loop that uses a known request_id (we monkey-patch new_id).
    import paari.runtime.loop as loop_mod
    original_new_id = loop_mod.new_id
    loop_mod.new_id = lambda: request_id_marker
    try:
        response = await _loop().run(identity, "find SKU-001", amount_paise=1000)
    finally:
        loop_mod.new_id = original_new_id
    assert response.status.value == "completed"

    # Verify an EXECUTED audit row exists for this request_id.
    from paari.db.engine import get_session_maker
    maker = get_session_maker()
    async with maker() as session:
        rows = (await session.execute(
            text("SELECT decision FROM audit_events WHERE request_id = :rid"),
            {"rid": request_id_marker},
        )).fetchall()
    decisions = {r.decision for r in rows}
    assert "EXECUTED" in decisions
