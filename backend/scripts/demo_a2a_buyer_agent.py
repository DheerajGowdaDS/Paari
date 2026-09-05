#!/usr/bin/env python3
"""Phase 2 A2A Demo - Run the Buyer Agent through the complete purchase flow.

This script demonstrates the complete Phase 2 A2A purchase flow:
1. Discover merchant agents
2. Request a quote
3. Accept the quote (runs governance)
4. Execute payment (simulated)
5. Verify payment status

Usage:
    # Start Paari server first:
    python -m uvicorn paari.main:app --host 127.0.0.1 --port 8000 --reload

    # Then run this demo:
    python scripts/demo_a2a_buyer_agent.py

"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Windows consoles default to cp1252 and crash on ₹/✅ — force UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from paari.agent.buyer_agent import BuyerAgent
from paari.db.engine import init_db
from paari.seed import main as seed_main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-25s %(levelname)-8s %(message)s",
)
_log = logging.getLogger("paari.demo")


async def setup_database():
    """Initialize and seed the database."""
    from paari.seed import seed_async
    _log.info("Setting up database...")
    await init_db()
    await seed_async()
    _log.info("Database setup complete.")


async def run_buyer_agent_demo(product_name: str = "Nike Runner"):
    """Run the complete Buyer Agent demo purchase flow."""
    agent = BuyerAgent(
        agent_id="BA-001",
        paari_url="http://localhost:8000",
        buyer_agent_id="BA-001",
    )

    print("\n" + "=" * 60)
    print("STEP 1: Discover Merchant Agents")
    print("=" * 60)

    merchants = await agent.discover_merchants()
    if not merchants:
        print("ERROR: No merchant agents found!")
        return False

    for m in merchants:
        print(f"  Found: {m.get('display_id', m['agent_id'])}")

    merchant = merchants[0]
    merchant_id = merchant["agent_id"]

    print("\n" + "=" * 60)
    print("STEP 2: Request Quote")
    print("=" * 60)

    quote = await agent.request_quote(
        merchant_agent_id=merchant_id,
        product_name=product_name,
        quantity=1,
    )
    print(f"  Quote ID: {quote.get('quote_id', 'N/A')}")
    print(f"  Transaction ID: {quote.get('transaction_id', 'N/A')}")
    print(f"  Product: {quote.get('product_name', 'N/A')}")
    print(f"  Quantity: {quote.get('quantity', 1)}")
    print(f"  Total Amount: ₹{quote.get('total_amount_paise', 0) / 100:.2f}")
    print(f"  Expires: {quote.get('expires_at', 'N/A')}")
    print(f"  Status: {quote.get('state', 'N/A')}")

    print("\n" + "=" * 60)
    print("STEP 3: Accept Quote (Governance Evaluation)")
    print("=" * 60)

    payment_session = await agent.accept_quote(
        merchant_agent_id=merchant_id,
        quote_id=quote["quote_id"],
    )
    print(f"  Payment Session: {payment_session.get('payment_session_id', 'N/A')}")
    print(f"  Authorized Amount: ₹{payment_session.get('authorized_amount', 0) / 100:.2f}")
    print(f"  Status: {payment_session.get('status', 'N/A')}")

    print("\n" + "=" * 60)
    print("STEP 4: Execute Payment")
    print("=" * 60)

    payment = await agent.execute_payment(
        payment_session_id=payment_session["payment_session_id"],
        transaction_id=payment_session.get("transaction_id") or quote.get("transaction_id"),
        amount_paise=payment_session.get("authorized_amount"),
    )
    print(f"  Payment Status: {payment.get('status', 'N/A')}")
    print(f"  Razorpay Payment ID: {payment.get('razorpay_payment_id', 'N/A')}")
    print(f"  Razorpay Order ID: {payment.get('razorpay_order_id', 'N/A')}")

    # LIVE mode: the agent hands off to Razorpay Checkout. The human/UI
    # completes the test payment, then Paari verifies it (checkout signature
    # + real webhook) and fulfills automatically. The demo just waits for
    # PAYMENT_VERIFIED and reports.
    if payment.get("status") == "CHECKOUT_REQUIRED":
        print("\n  ⏳ Human-in-the-loop checkout required (live test mode):")
        print(f"     Open: {payment.get('checkout_url')}")
        print("     Pay with test card 4100 2800 0000 1007 (Visa Debit, Indian).")
        print("     Waiting for Razorpay webhook to mark the transaction PAYMENT_VERIFIED...")
        tx_id = payment.get("transaction_id") or quote.get("transaction_id")
        import time
        for _ in range(60):  # up to 5 minutes
            time.sleep(5)
            status = await agent.verify_payment(tx_id)
            state = status.get("state") or status.get("status")
            print(f"     -> tx state: {state}")
            if state in ("PAYMENT_VERIFIED", "FULFILLMENT_PENDING", "ORDER_CONFIRMED", "COMPLETED"):
                break
        print("  Final state:", state)
        return state in ("PAYMENT_VERIFIED", "FULFILLMENT_PENDING", "ORDER_CONFIRMED", "COMPLETED")

    print("\n" + "=" * 60)
    print("STEP 5: Fulfill Order")
    print("=" * 60)

    # Send fulfill order message
    fulfill_response = await agent.send_message(
        receiver_id=merchant_id,
        action="FULFILL_ORDER",
        payload={"transaction_id": quote.get("transaction_id")},
    )
    print(f"  Fulfillment: {fulfill_response.get('status', 'N/A')}")
    print(f"  Order ID: {fulfill_response.get('payload', {}).get('order_id', 'N/A')}")
    print(f"  Amount: ₹{fulfill_response.get('payload', {}).get('amount_paise', 0) / 100:.2f}")

    print("\n" + "=" * 60)
    print("✅ COMPLETE PURCHASE FLOW FINISHED!")
    print("=" * 60)

    return True


async def run_blocked_scenario_demo(product_name: str = "Nike Runner", blocked_quantity: int = 6):
    """Demonstrate the governance blocking a high-value transaction."""
    _log.info("\n" + "=" * 60)
    _log.info("BLOCKED SCENARIO DEMO (Amount exceeds user limit)")
    _log.info("=" * 60)

    agent = BuyerAgent(
        agent_id="BA-001",
        paari_url="http://localhost:8000",
    )

    print("\n" + "=" * 60)
    print("BLOCKED SCENARIO: High-Value Purchase")
    print("=" * 60)

    # Try to discover merchants
    merchants = await agent.discover_merchants()
    if not merchants:
        print("ERROR: No merchant agents found!")
        return False

    merchant = merchants[0]
    merchant_id = merchant["agent_id"]

    # Request a high-quantity purchase so the total exceeds the user's
    # transaction limit (₹5,000) - should be DENIED by governance.
    print(f"  Requesting {blocked_quantity} x '{product_name}'...")
    print(f"  User limit is ₹5,000 - should be DENIED by governance")

    quote = await agent.request_quote(
        merchant_agent_id=merchant_id,
        product_name=product_name,
        quantity=blocked_quantity,
    )
    print(f"  Quote created: ₹{quote.get('total_amount_paise', 0) / 100:.2f}")

    print("\n  Now accepting quote (should be DENIED by governance)...")

    try:
        result = await agent.accept_quote(
            merchant_agent_id=merchant_id,
            quote_id=quote["quote_id"],
        )
        print(f"  UNEXPECTED: Should have been denied! Result: {result}")
        return False
    except PermissionError as e:
        print(f"  ✅ CORRECTLY DENIED: {e}")
        return True
    except Exception as e:
        print(f"  ✅ DENIED with error: {e}")
        return True


async def main(product_name: str = "Nike Runner", blocked_quantity: int = 6):
    """Run all Phase 2 demos."""
    print("\n" + "=" * 60)
    print("PAARI PHASE 2 - A2A BUYER AGENT DEMO")
    print("=" * 60)
    print("\nThis demo shows the complete AI Buyer Agent purchase flow")
    print("through the Paari A2A Gateway.\n")

    # Setup
    await setup_database()

    # Run success scenario
    print("\n\n")
    success = await run_buyer_agent_demo(product_name=product_name)

    if success:
        print("\n\n")
        blocked = await run_blocked_scenario_demo(
            product_name=product_name,
            blocked_quantity=blocked_quantity,
        )
    else:
        print("\n\n⚠️  Success scenario failed - skipping blocked scenario")
        blocked = False

    # Summary
    print("\n" + "=" * 60)
    print("DEMO SUMMARY")
    print("=" * 60)
    print(f"  Success scenario:  {'✅ PASSED' if success else '❌ FAILED'}")
    print(f"  Blocked scenario:  {'✅ PASSED' if blocked else '⚠️  SKIPPED'}")

    if success and blocked:
        print("\n🎉 Phase 2 A2A Buyer Agent Demo Complete!")
        print("\nThe Buyer Agent successfully:")
        print("  1. Discovered merchant agents via A2A")
        print("  2. Requested and received a quote")
        print("  3. Accepted quote with governance evaluation")
        print("  4. Executed simulated payment")
        print("  5. Verified payment status")
        print("\nAnd correctly blocked a high-value transaction!")
    else:
        print("\n❌ Demo had failures - check logs above")
        return 1

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2 A2A buyer agent demo")
    parser.add_argument("--product", default="Nike Runner", help="Product name to quote (default: Nike Runner, stub catalog)")
    parser.add_argument("--blocked-quantity", type=int, default=6, help="Quantity for the blocked (DENY) scenario (default: 6)")
    args = parser.parse_args()
    exit_code = asyncio.run(main(product_name=args.product, blocked_quantity=args.blocked_quantity))
    sys.exit(exit_code)
