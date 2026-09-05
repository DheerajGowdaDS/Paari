#!/usr/bin/env python3
"""Phase 2 A2A Demo - Test the Buyer Agent flow directly without HTTP.

This script tests the complete Phase 2 A2A purchase flow by calling
the Merchant Agent directly (in-process), bypassing HTTP for faster testing.

Usage:
    python scripts/demo_a2a_buyer_agent_direct.py

"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Windows consoles default to cp1252 and crash on ₹/✅ — force UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# This demo runs the merchant agent in-process — force stub mode so it
# searches the offline fixture catalog regardless of .env / shell exports.
os.environ["PAARI_SHOPIFY_MODE"] = "stub"
os.environ["PAARI_RAZORPAY_MODE"] = "stub"

from paari.agent.merchant_agent import MerchantAgent
from paari.a2a.types import A2AAction, A2AMessage
from paari.db.engine import init_db
from paari.seed import seed_async

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-25s %(levelname)-8s %(message)s",
)
_log = logging.getLogger("paari.demo")


async def setup_database():
    """Initialize and seed the database."""
    _log.info("Setting up database...")
    await init_db()
    await seed_async()
    _log.info("Database setup complete.")


class MockBuyerAgent:
    """Mock Buyer Agent for direct testing (bypasses HTTP)."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    async def send_message(self, merchant_agent: MerchantAgent, message: A2AMessage) -> dict[str, Any]:
        """Send A2A message to merchant agent and get response."""
        response = await merchant_agent.handle_message(message)
        return {
            "status": response.status.value,
            "payload": response.payload,
            "error": response.error,
        }


async def run_direct_demo():
    """Run the Buyer Agent demo directly (no HTTP)."""
    _log.info("=" * 60)
    _log.info("PHASE 2 A2A BUYER AGENT DEMO (DIRECT)")
    _log.info("=" * 60)

    # Setup mock buyer agent
    buyer = MockBuyerAgent(agent_id="BA-001")
    merchant = MerchantAgent(agent_id="MA-001", merchant_id="MER-001")

    print("\n" + "=" * 60)
    print("STEP 1: Discover Merchant Agent")
    print("=" * 60)

    discover_msg = A2AMessage(
        sender_id="BA-001",
        receiver_id="MA-001",
        action=A2AAction.DISCOVER,
        payload={},
    )
    result = await buyer.send_message(merchant, discover_msg)
    print(f"  Status: {result['status']}")
    if result['payload']:
        print(f"  Merchant: {result['payload'].get('merchant_name', 'N/A')}")
        print(f"  Capabilities: {result['payload'].get('capabilities', [])[:3]}...")

    print("\n" + "=" * 60)
    print("STEP 2: Request Quote (Rs 4,799)")
    print("=" * 60)

    quote_msg = A2AMessage(
        sender_id="BA-001",
        receiver_id="MA-001",
        action=A2AAction.REQUEST_QUOTE,
        payload={
            "product_name": "Nike Runner",
            "quantity": 1,
            "buyer_agent_id": "BA-001",
        },
    )
    result = await buyer.send_message(merchant, quote_msg)
    print(f"  Status: {result['status']}")
    quote_id = result['payload'].get('quote_id')
    tx_id = result['payload'].get('transaction_id')
    print(f"  Quote ID: {quote_id}")
    print(f"  Transaction ID: {tx_id}")
    print(f"  Amount: Rs {result['payload'].get('total_amount_paise', 0) / 100:.2f}")
    print(f"  Expires: {result['payload'].get('expires_at', 'N/A')}")

    print("\n" + "=" * 60)
    print("STEP 3: Accept Quote (Governance Evaluation)")
    print("=" * 60)

    accept_msg = A2AMessage(
        sender_id="BA-001",
        receiver_id="MA-001",
        action=A2AAction.ACCEPT_QUOTE,
        payload={
            "quote_id": quote_id,
            "buyer_agent_id": "BA-001",
        },
    )
    result = await buyer.send_message(merchant, accept_msg)
    print(f"  Status: {result['status']}")

    if result['status'] == 'SUCCESS':
        print(f"  Payment Session ID: {result['payload'].get('payment_session_id')}")
        print(f"  Authorized Amount: Rs {result['payload'].get('authorized_amount', 0) / 100:.2f}")
        print(f"  Expires: {result['payload'].get('expires_at')}")
        payment_session_id = result['payload'].get('payment_session_id')
        return payment_session_id
    else:
        print(f"  Error: {result.get('error')}")
        return None


async def run_blocked_demo():
    """Demonstrate governance blocking a high-value transaction."""
    _log.info("\n" + "=" * 60)
    _log.info("BLOCKED SCENARIO DEMO (Amount exceeds user limit)")
    _log.info("=" * 60)

    buyer = MockBuyerAgent(agent_id="BA-001")
    merchant = MerchantAgent(agent_id="MA-001", merchant_id="MER-001")

    print("\n" + "=" * 60)
    print("BLOCKED SCENARIO: High-Value Purchase (6 x Nike Runner)")
    print("=" * 60)
    print("  User limit is Rs 5,000 - should be DENIED by governance\n")

    # Request quote for 6 units of Nike Runner (₹4,799 each = ₹28,794)
    quote_msg = A2AMessage(
        sender_id="BA-001",
        receiver_id="MA-001",
        action=A2AAction.REQUEST_QUOTE,
        payload={
            "product_name": "Nike Runner",
            "quantity": 6,
            "buyer_agent_id": "BA-001",
        },
    )
    result = await buyer.send_message(merchant, quote_msg)
    quote_id = result['payload'].get('quote_id')
    print(f"  Quote created: Rs {result['payload'].get('total_amount_paise', 0) / 100:.2f}")

    # Try to accept - should be DENIED
    accept_msg = A2AMessage(
        sender_id="BA-001",
        receiver_id="MA-001",
        action=A2AAction.ACCEPT_QUOTE,
        payload={
            "quote_id": quote_id,
            "buyer_agent_id": "BA-001",
        },
    )
    result = await buyer.send_message(merchant, accept_msg)
    print(f"  Status: {result['status']}")

    if result['status'] == 'DENIED':
        print(f"  ✅ CORRECTLY DENIED: {result.get('error')}")
        return True
    else:
        print(f"  ⚠️  UNEXPECTED: Should have been denied!")
        return False


async def main():
    """Run all Phase 2 demos."""
    print("\n" + "=" * 60)
    print("PAARI PHASE 2 - A2A BUYER AGENT DEMO (DIRECT)")
    print("=" * 60)
    print("\nThis demo tests the complete AI Buyer Agent purchase flow")
    print("by calling the Merchant Agent directly (no HTTP required).\n")

    # Setup
    await setup_database()

    # Run success scenario
    print("\n\n")
    payment_session_id = await run_direct_demo()

    if payment_session_id:
        print("\n\n")
        blocked = await run_blocked_demo()
    else:
        blocked = False

    # Summary
    print("\n" + "=" * 60)
    print("DEMO SUMMARY")
    print("=" * 60)
    print(f"  Success scenario:  {'✅ PASSED' if payment_session_id else '❌ FAILED'}")
    print(f"  Blocked scenario:  {'✅ PASSED' if blocked else '⚠️  SKIPPED'}")

    if payment_session_id and blocked:
        print("\n🎉 Phase 2 A2A Buyer Agent Demo Complete!")
        print("\nThe Buyer Agent successfully:")
        print("  1. Discovered merchant agents via A2A")
        print("  2. Requested and received a quote")
        print("  3. Accepted quote with governance evaluation")
        print("  4. Payment session created successfully")
        print("\nAnd correctly blocked a high-value transaction!")
    else:
        print("\n❌ Demo had failures - check logs above")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
