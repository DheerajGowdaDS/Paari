"""Showcase 4 proof cases — pytest version of scripts/showcase.py.

All cases drive the real Gateway/Payment/Governance stack (no mocks of governance).
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from paari.dashboard.session import create_session
from paari.db.engine import get_session_maker
from paari.main import app


async def _make_quote_tx(session, tag: str, quote_amt: int, tx_amt: int, buyer_id: str = "BA-001"):
    qid = f"Q-SHOWCASE-{tag}-{secrets.token_hex(2).upper()}"
    txid = str(uuid.uuid4())
    did = f"TXN-SHOWCASE-{tag}-{secrets.token_hex(2).upper()}"
    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    await session.execute(
        text(
            "INSERT INTO quotes (id, transaction_id, merchant_id, amount_paise, expires_at, state) VALUES (:id,:tx,:mid,:amt,:exp,'ACCEPTED')"
        ),
        {"id": qid, "tx": txid, "mid": "MER-001", "amt": quote_amt, "exp": exp},
    )
    await session.execute(
        text(
            "INSERT INTO transactions (id, display_id, merchant_id, buyer_agent_id, merchant_agent_id, quote_id, amount_paise, currency, state, policy_version) VALUES (:id,:did,'MER-001',:buyer,'MA-001',:qid,:amt,'INR','CREATED','v1')"
        ),
        {"id": txid, "did": did, "buyer": buyer_id, "qid": qid, "amt": tx_amt},
    )
    await session.commit()
    return txid, did, qid


async def _ensure_review_user(session):
    await session.execute(
        text(
            "INSERT OR IGNORE INTO users (id, display_id, name, status) VALUES ('USER-REVIEW','USER-REVIEW','Review Buyer','ACTIVE')"
        )
    )
    await session.execute(
        text(
            "INSERT OR REPLACE INTO user_policies (id, user_id, max_transaction_amount, daily_spending_limit, autonomous_payment, confirmation_threshold) VALUES ('UP-REVIEW','USER-REVIEW',1000000,2000000,0,500000)"
        )
    )
    caps = json.dumps(
        [
            "catalog.read",
            "inventory.read",
            "product.read",
            "quote.request",
            "quote.accept",
            "payment.request",
            "payment.execute",
            "order.read",
        ]
    )
    await session.execute(
        text(
            "INSERT OR REPLACE INTO agents (id, merchant_id, agent_type, capabilities_json, display_id, owner_id, status) VALUES ('BA-REVIEW',NULL,'BUYER',:caps,'BA-REVIEW','USER-REVIEW','ACTIVE')"
        ),
        {"caps": caps},
    )
    await session.commit()
    return "BA-REVIEW"


async def _count(session, table: str, txid: str) -> int:
    r = (
        await session.execute(
            text(f"SELECT COUNT(*) AS c FROM {table} WHERE transaction_id=:t"), {"t": txid}
        )
    ).first()
    return int(r.c) if r else 0


@pytest.mark.asyncio
async def test_case_a_allow_bounded():
    maker = get_session_maker()
    async with maker() as s:
        txid, did, qid = await _make_quote_tx(s, "A", 479_900, 479_900)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/gateway/governance/evaluate", json={"transaction_id": did})
        assert r.status_code == 200
        assert r.json()["decision"] == "ALLOW"
        r = await client.post("/payments/create", json={"transaction_id": did})
        assert r.status_code == 200
        assert r.json()["authorized"] is True
        assert r.json()["authorized_amount"] == 479_900
        sid = r.json()["session_display_id"]
        r2 = await client.post("/payments/simulate", json={"payment_session_id": sid})
        assert r2.status_code == 200
        assert r2.json()["status"] == "VERIFIED"
    async with maker() as s:
        assert await _count(s, "payment_sessions", txid) == 1
        assert await _count(s, "payment_capabilities", txid) == 1
        state = (
            (await s.execute(text("SELECT state FROM transactions WHERE id=:id"), {"id": txid}))
            .first()
            .state
        )
        assert state == "PAYMENT_VERIFIED"


@pytest.mark.asyncio
async def test_case_b_deny_no_session_no_adapter():
    maker = get_session_maker()
    async with maker() as s:
        txid, did, qid = await _make_quote_tx(s, "B", 479_900, 799_900)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/gateway/governance/evaluate", json={"transaction_id": did})
        assert r.json()["decision"] == "DENY"
        r = await client.post("/payments/create", json={"transaction_id": did})
        assert r.json()["authorized"] is False
    async with maker() as s:
        assert await _count(s, "payment_sessions", txid) == 0
        assert await _count(s, "payment_capabilities", txid) == 0
        from paari.payment.service import get_payment_service

        svc = get_payment_service()
        order = await svc.create_razorpay_order(did, "PS-FORGED")
        assert order.success is False
        assert "invalid_transaction_state" in (order.reason or "")


@pytest.mark.asyncio
async def test_case_c_review_then_approve():
    maker = get_session_maker()
    async with maker() as s:
        reviewer = await _ensure_review_user(s)
        txid, did, qid = await _make_quote_tx(s, "C", 479_900, 479_900, buyer_id=reviewer)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/gateway/governance/evaluate", json={"transaction_id": did})
        assert r.json()["decision"] == "REVIEW"
        from paari.review.service import REVIEW

        pending = {"tool_name": "search_products", "arguments": {"query": "snowboard", "limit": 5}}
        review = await REVIEW.create(
            merchant_id="MER-001",
            transaction_id=txid,
            triggered_by="POLICY",
            reason="test review",
            pending_step=pending,
            gateway_context={
                "identity": {
                    "agent_id": reviewer,
                    "agent_type": "BUYER",
                    "capabilities": ["catalog.read"],
                    "policy_version": "v1",
                },
                "merchant_id": "MER-001",
                "tx_context": {"amount_paise": 479900},
                "merchant_context": {},
            },
        )
        async with maker() as s:
            await s.execute(
                text(
                    "UPDATE user_policies SET autonomous_payment=1, confirmation_threshold=1000000 WHERE user_id='USER-REVIEW'"
                )
            )
            await s.execute(
                text("UPDATE transactions SET state='REVIEW_REQUIRED' WHERE id=:id"), {"id": txid}
            )
            await s.commit()
        await REVIEW.decide(review_id=review.id, decision="APPROVE", decided_by="tester", note="ok")
        r2 = await client.post("/payments/create", json={"transaction_id": did})
        assert r2.status_code == 200
        assert r2.json()["authorized"] is True
        async with maker() as s:
            await s.execute(
                text("UPDATE user_policies SET autonomous_payment=0 WHERE user_id='USER-REVIEW'")
            )
            await s.commit()


@pytest.mark.asyncio
async def test_case_d_payment_failed_no_fulfillment():
    maker = get_session_maker()
    async with maker() as s:
        txid, did, qid = await _make_quote_tx(s, "D", 479_900, 479_900)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/gateway/governance/evaluate", json={"transaction_id": did})
        assert r.json()["decision"] == "ALLOW"
        r = await client.post("/payments/create", json={"transaction_id": did})
        sid = r.json()["session_display_id"]
        r2 = await client.post(
            "/payments/simulate", json={"payment_session_id": sid, "simulate_failure": True}
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "FAILED"
        assert r2.json()["success"] is False
    async with maker() as s:
        state = (
            (await s.execute(text("SELECT state FROM transactions WHERE id=:id"), {"id": txid}))
            .first()
            .state
        )
        assert state == "PAYMENT_FAILED"
        assert state != "ORDER_CONFIRMED"
        rows = (
            await s.execute(
                text("SELECT event_type FROM payment_events WHERE transaction_id=:t"), {"t": txid}
            )
        ).fetchall()
        assert any(r.event_type == "payment.failed" for r in rows)


@pytest.mark.asyncio
async def test_dashboard_transaction_view_renders():
    maker = get_session_maker()
    async with maker() as s:
        txid, did, qid = await _make_quote_tx(s, "DASH", 479_900, 479_900)
        # trigger governance to generate audit rows
        from paari.governance_engine.context import GovernanceContext
        from paari.governance_engine.evaluator import get_governance_engine

        ctx = await GovernanceContext.load(s, txid)
        eng = get_governance_engine()
        await eng.evaluate(ctx, s)
        await s.commit()
    token = create_session("merchant@demo.local", "merchant-demo-001")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/dashboard/transactions/{did}", cookies={"paari_session": token})
        assert r.status_code == 200
        assert did in r.text
        assert "Governance" in r.text
