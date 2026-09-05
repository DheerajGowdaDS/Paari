"""Post-verification settlement: dispatch merchant fulfillment.

Runs after a transaction reaches PAYMENT_VERIFIED through any trusted path
(real Razorpay webhook, checkout verification, demo simulation). Sends
FULFILL_ORDER to the merchant agent, which creates the Shopify order and
walks PAYMENT_VERIFIED -> ORDER_CONFIRMED -> COMPLETED.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

_log = logging.getLogger("paari.payment.settle")


async def settle_verified_transaction(transaction_id: str) -> dict[str, Any]:
    """Fulfill a verified transaction via the merchant agent.

    Args:
        transaction_id: Transaction UUID or display_id.

    Returns:
        Dict with fulfilled flag plus order_id or reason. Never raises for
        expected rejections; raises only on operational failures.
    """
    from paari.a2a.types import A2AAction, A2AMessage, A2AStatus
    from paari.agent.merchant_agent import get_merchant_agent
    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        row = (
            await session.execute(
                text("SELECT id, state FROM transactions WHERE id = :x OR display_id = :x"),
                {"x": transaction_id},
            )
        ).first()
        if row is None:
            return {"fulfilled": False, "reason": "transaction_not_found"}
        if row.state != "PAYMENT_VERIFIED":
            return {"fulfilled": False, "reason": f"not_ready:{row.state}"}
        tx_id = row.id
        # The one-time capability is consumed at verification (any trusted path
        # reaches settlement only from PAYMENT_VERIFIED). Mirrors the explicit
        # /payments/verify path so the bounded-capability ledger stays true.
        await session.execute(
            text(
                "UPDATE payment_capabilities SET used=1 "
                "WHERE (transaction_id = :x OR transaction_id = :tid) AND used=0"
            ),
            {"x": transaction_id, "tid": tx_id},
        )
        await session.commit()

    agent = get_merchant_agent("MA-001")
    message = A2AMessage(
        sender_id="paari-gateway",
        receiver_id="MA-001",
        action=A2AAction.FULFILL_ORDER,
        payload={"transaction_id": tx_id},
    )
    try:
        response = await agent.handle_fulfill_order(message)
    except Exception as exc:
        _log.warning("Fulfillment dispatch failed for %s: %s", transaction_id, exc)
        return {"fulfilled": False, "reason": f"dispatch_failed:{exc}"}
    if response.status in (A2AStatus.ORDER_CONFIRMED, A2AStatus.SUCCESS):
        order_id = (response.payload or {}).get("order_id")
        return {"fulfilled": True, "order_id": order_id}
    return {"fulfilled": False, "reason": response.error or "fulfillment_rejected"}
