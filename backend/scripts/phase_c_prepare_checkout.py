"""Phase C — prepare a real checkout transaction.

Runs discover -> request_quote -> accept_quote and STOPS, leaving the
transaction in PAYMENT_PENDING with an ACTIVE session and NO Razorpay order.
The checkout page then creates the real Razorpay order when opened, so the
human can pay with a real test card and the REAL webhook verifies + settles.

Usage:  python scripts/phase_c_prepare_checkout.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from paari.agent.buyer_agent import BuyerAgent

PAARI_URL = "http://127.0.0.1:8000"


async def main() -> int:
    agent = BuyerAgent(agent_id="BA-001", paari_url=PAARI_URL, buyer_agent_id="BA-001")

    print("STEP 1: discover merchants")
    merchants = await agent.discover_merchants()
    if not merchants:
        print("ERROR: no merchant agents found")
        return 1
    merchant = merchants[0]
    merchant_id = merchant["agent_id"]
    print(f"  merchant: {merchant_id}")

    print("STEP 2: request quote (snowboard bundle, qty 1)")
    quote = await agent.request_quote(
        merchant_agent_id=merchant_id,
        product_name="snowboard",
        quantity=1,
    )
    quote_id = quote.get("quote_id")
    print(f"  quote_id: {quote_id}")
    print(f"  amount: Rs {quote.get('total_amount_paise', 0) / 100:.2f}")

    print("STEP 3: accept quote (governance)")
    result = await agent.accept_quote(
        merchant_agent_id=merchant_id,
        quote_id=quote_id,
    )
    if result.get("requires_review"):
        print(f"  REVIEW REQUIRED: {result.get('reason')}")
        return 1

    tx_id = result.get("transaction_id")
    session_id = result.get("payment_session_id")
    print(f"  transaction_id: {tx_id}")
    print(f"  payment_session_id: {session_id}")
    print(f"  authorized_amount: Rs {result.get('authorized_amount', 0) / 100:.2f}")
    print()
    print("CHECKOUT URL:")
    print(f"  http://127.0.0.1:8000/checkout/{tx_id}")
    print()
    with open("phase_c_checkout.json", "w", encoding="utf-8") as fh:
        json.dump(
            {"transaction_id": tx_id, "quote_id": quote_id, "payment_session_id": session_id},
            fh,
            indent=2,
        )
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(asyncio.run(main()))