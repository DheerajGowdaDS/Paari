"""Demo: End-to-end payment flow with Razorpay.

Demonstrates:
1. Success path: ₹4,799 transaction → ALLOW → Razorpay → verified → FULFILLED
2. Block path: ₹25,000 transaction → DENY → no Razorpay call

Usage:
    python scripts/demo_payment_flow.py
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows cp1252 console cannot encode the emoji/₹ glyphs used below.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import text

from paari.config import settings
from paari.db.engine import get_session_maker, init_db
from paari.governance_engine.context import GovernanceContext
from paari.governance_engine.evaluator import get_governance_engine
from paari.governance_engine.state_machine import transition
from paari.payment.service import PaymentService


async def setup_demo_transactions() -> tuple[str, str]:
    """Create demo transactions with proper quote context for success and block scenarios.

    Returns:
        Tuple of (success_tx_id, blocked_tx_id)
    """
    maker = get_session_maker()
    async with maker() as session:
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=1)

        success_tx_id = f"demo-success-{secrets.token_hex(4)}"
        blocked_tx_id = f"demo-blocked-{secrets.token_hex(4)}"

        success_quote_id = f"demo-quote-success-{secrets.token_hex(4)}"
        blocked_quote_id = f"demo-quote-blocked-{secrets.token_hex(4)}"

        demo_buyer_id = f"demo-buyer-{secrets.token_hex(4)}"
        await session.execute(
            text(
                "INSERT OR IGNORE INTO agents "
                "(id, display_id, agent_type, capabilities_json, owner_id, status) "
                "VALUES (:id, :display_id, :type, :caps, :owner, :status)"
            ),
            {
                "id": demo_buyer_id,
                "display_id": f"BA-DEMO-{secrets.token_hex(4).upper()}",
                "type": "BUYER",
                "caps": '["catalog.read", "inventory.read", "product.read", "quote.create", "deal.negotiate", "payment.request"]',
                "owner": "USER-001",
                "status": "ACTIVE",
            },
        )

        await session.execute(
            text(
                "INSERT OR IGNORE INTO transactions "
                "(id, display_id, merchant_id, buyer_agent_id, quote_id, amount_paise, currency, state, policy_version) "
                "VALUES (:id, :display_id, :merchant, :buyer, :quote, :amount, :currency, :state, :pv)"
            ),
            {
                "id": success_tx_id,
                "display_id": f"TXN-SUCCESS-{secrets.token_hex(4).upper()}",
                "merchant": "MER-001",
                "buyer": demo_buyer_id,
                "quote": success_quote_id,
                "amount": 479900,
                "currency": "INR",
                "state": "GOVERNANCE_PENDING",
                "pv": "v1",
            },
        )

        await session.execute(
            text(
                "INSERT OR IGNORE INTO quotes "
                "(id, transaction_id, merchant_id, amount_paise, expires_at, state) "
                "VALUES (:id, :tx_id, :merchant, :amount, :expires, :state)"
            ),
            {
                "id": success_quote_id,
                "tx_id": success_tx_id,
                "merchant": "MER-001",
                "amount": 479900,
                "expires": expires_at.isoformat(),
                "state": "ACCEPTED",
            },
        )

        await session.execute(
            text(
                "INSERT OR IGNORE INTO transactions "
                "(id, display_id, merchant_id, buyer_agent_id, quote_id, amount_paise, currency, state, policy_version) "
                "VALUES (:id, :display_id, :merchant, :buyer, :quote, :amount, :currency, :state, :pv)"
            ),
            {
                "id": blocked_tx_id,
                "display_id": f"TXN-BLOCKED-{secrets.token_hex(4).upper()}",
                "merchant": "MER-001",
                "buyer": demo_buyer_id,
                "quote": blocked_quote_id,
                "amount": 2500000,
                "currency": "INR",
                "state": "GOVERNANCE_PENDING",
                "pv": "v1",
            },
        )

        await session.execute(
            text(
                "INSERT OR IGNORE INTO quotes "
                "(id, transaction_id, merchant_id, amount_paise, expires_at, state) "
                "VALUES (:id, :tx_id, :merchant, :amount, :expires, :state)"
            ),
            {
                "id": blocked_quote_id,
                "tx_id": blocked_tx_id,
                "merchant": "MER-001",
                "amount": 2500000,
                "expires": expires_at.isoformat(),
                "state": "ACCEPTED",
            },
        )

        await session.commit()

    return success_tx_id, blocked_tx_id


async def run_success_scenario(service: PaymentService, tx_id: str) -> dict:
    """Run the success payment scenario.

    Flow:
    1. Authorize payment (governance ALLOW)
    2. Create Razorpay order
    3. Simulate webhook
    4. Verify payment
    """
    print(f"\n{'='*60}")
    print(f"SUCCESS SCENARIO: Transaction {tx_id[:20]}...")
    print(f"{'='*60}")

    print("\n[1/4] Authorizing payment through governance...")
    result = await service.authorize_payment(tx_id)

    if not result.authorized:
        print(f"    ❌ Authorization failed: {result.reason}")
        return {"success": False, "reason": result.reason}

    print(f"    ✅ Authorized: session={result.session_display_id}, amount=₹{result.authorized_amount/100:.2f}")

    print("\n[2/4] Creating Razorpay order...")
    order_result = await service.create_razorpay_order(tx_id, result.session_id)

    if not order_result.success:
        print(f"    ❌ Order creation failed: {order_result.reason}")
        return {"success": False, "reason": order_result.reason}

    print(f"    ✅ Order created: {order_result.order_id}")

    print("\n[3/4] Simulating payment webhook (payment.captured)...")
    await service.simulate_webhook(
        event_type="payment.captured",
        payment_id=f"pay_{secrets.token_hex(8)}",
        order_id=order_result.order_id,
        amount=result.authorized_amount,
    )
    print(f"    ✅ Webhook simulated")

    print("\n[4/4] Verifying payment state...")
    maker = get_session_maker()
    async with maker() as session:
        row = (
            await session.execute(
                text("SELECT state, razorpay_order_id, razorpay_payment_id FROM transactions WHERE id = :tid"),
                {"tid": tx_id},
            )
        ).first()

        if row:
            print(f"    Transaction state: {row.state}")
            print(f"    Razorpay order: {row.razorpay_order_id}")
            print(f"    Razorpay payment: {row.razorpay_payment_id}")

            if row.state == "PAYMENT_VERIFIED":
                print("\n    ✅ PAYMENT VERIFIED - Transaction fulfilled!")
                return {"success": True, "state": row.state}
            else:
                print(f"\n    ⚠️  Unexpected state: {row.state}")
                return {"success": False, "reason": f"unexpected_state: {row.state}"}

    return {"success": False, "reason": "transaction_not_found"}


async def run_blocked_scenario(service: PaymentService, tx_id: str) -> dict:
    """Run the blocked payment scenario.

    Flow:
    1. Authorize payment (governance DENY for amount > limit)
    2. Verify no Razorpay order created
    """
    print(f"\n{'='*60}")
    print(f"BLOCKED SCENARIO: Transaction {tx_id[:20]}...")
    print(f"{'='*60}")

    print("\n[1/2] Attempting authorization (should be DENIED)...")
    result = await service.authorize_payment(tx_id)

    if result.authorized:
        print(f"    ⚠️  Authorization succeeded unexpectedly!")
        return {"success": False, "reason": "should_have_been_denied"}

    print(f"    ✅ Correctly denied: {result.reason}")

    print("\n[2/2] Verifying no Razorpay order was created...")
    maker = get_session_maker()
    async with maker() as session:
        row = (
            await session.execute(
                text("SELECT state, razorpay_order_id FROM transactions WHERE id = :tid"),
                {"tid": tx_id},
            )
        ).first()

        if row:
            print(f"    Transaction state: {row.state}")
            print(f"    Razorpay order: {row.razorpay_order_id}")

            if row.razorpay_order_id is None:
                print("\n    ✅ Correctly blocked - no Razorpay call made!")
                return {"success": True, "state": row.state}
            else:
                print(f"\n    ⚠️  Unexpected: Razorpay order was created for denied transaction")
                return {"success": False, "reason": "order_created_for_denied"}

    return {"success": False, "reason": "transaction_not_found"}


async def main_async() -> None:
    """Run the complete demo."""
    print("\n" + "="*60)
    print("PAARI RAZORPAY PAYMENT FLOW DEMO")
    print("="*60)
    print(f"\nMode: {settings.razorpay_mode}")
    print(f"Razorpay Key: {settings.razorpay_key_id or '(not set)'}")

    print("\n[SETUP] Initializing database...")
    await init_db()
    print("    ✅ Database initialized")

    print("\n[SETUP] Creating demo transactions...")
    success_tx_id, blocked_tx_id = await setup_demo_transactions()
    print(f"    ✅ Success transaction: {success_tx_id[:20]}... (₹4,799)")
    print(f"    ✅ Blocked transaction: {blocked_tx_id[:20]}... (₹25,000)")

    service = PaymentService()

    success_result = await run_success_scenario(service, success_tx_id)
    blocked_result = await run_blocked_scenario(service, blocked_tx_id)

    print("\n" + "="*60)
    print("DEMO SUMMARY")
    print("="*60)
    print(f"\nSuccess scenario: {'✅ PASSED' if success_result['success'] else '❌ FAILED'}")
    print(f"Blocked scenario: {'✅ PASSED' if blocked_result['success'] else '❌ FAILED'}")

    if success_result["success"] and blocked_result["success"]:
        print("\n🎉 All scenarios passed!")
    else:
        print("\n⚠️  Some scenarios failed - review output above")
        sys.exit(1)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
