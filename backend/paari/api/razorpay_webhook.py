"""Razorpay webhook ingest endpoint.

POST /webhooks/razorpay
- Verifies HMAC-SHA256 signature
- Deduplicates via webhook_events unique constraint on event_id
- Processes the event via razorpay_handler
- Returns 200 immediately
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Header, Request, status

from paari.webhooks.razorpay_handler import persist_and_process_razorpay_webhook

_log = logging.getLogger("paari.webhooks.razorpay")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _notify_merchant_agent(transaction_id: str) -> None:
    """Blueprint Step 11: push PAYMENT_RESULT to the merchant agent.

    Best-effort: failures are logged, never raised (the webhook must ack 200).
    """
    try:
        from paari.a2a.types import A2AAction, A2AMessage
        from paari.agent.merchant_agent import get_merchant_agent
        from paari.db.engine import get_session_maker
        from sqlalchemy import text

        maker = get_session_maker()
        async with maker() as session:
            row = (
                await session.execute(
                    text("SELECT merchant_agent_id FROM transactions WHERE id = :id"),
                    {"id": transaction_id},
                )
            ).first()

        merchant_agent_id = (row.merchant_agent_id if row else None) or "MA-001"
        merchant_agent = get_merchant_agent(merchant_agent_id)

        message = A2AMessage(
            sender_id="paari-gateway",
            receiver_id=merchant_agent_id,
            action=A2AAction.PAYMENT_RESULT,
            payload={
                "transaction_id": transaction_id,
                "payment_status": "VERIFIED",
                "next_action": "FULFILL",
            },
        )

        await merchant_agent.handle_message(message)
        _log.info(
            "Notified merchant agent %s of payment for tx %s",
            merchant_agent_id,
            transaction_id,
        )
    except Exception as exc:
        _log.warning("Merchant agent notification failed: %s", exc)


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    x_razorpay_event_id: str = Header(default=""),
) -> dict[str, str]:
    """Handle an incoming Razorpay webhook.

    Verifies the signature and processes the event.
    In stub mode, signature verification may be skipped for testing.
    """
    from paari.config import settings
    from paari.tools.adapters.razorpay_stub import get_razorpay_stub_adapter

    body = await request.body()

    if settings.razorpay_mode == "live":
        if not x_razorpay_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Razorpay-Signature header",
            )

        from paari.adapters.razorpay_live import get_razorpay_adapter
        adapter = get_razorpay_adapter()

        is_valid = await adapter.verify_signature(body, x_razorpay_signature)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )
    else:
        adapter = get_razorpay_stub_adapter()
        if not x_razorpay_signature:
            _log.warning("Razorpay webhook missing signature in %s mode", settings.razorpay_mode)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    event_type = payload.get("event", "")
    event_id = payload.get("id", "") or x_razorpay_event_id

    if not event_type or not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing event type or id",
        )

    # The handler expects the inner payload (payment/order entity), not the
    # envelope — pass through the payload section so the entity is reachable.
    inner_payload = payload.get("payload", payload)

    try:
        result = await persist_and_process_razorpay_webhook(
            event_type=event_type,
            event_id=event_id,
            payload=inner_payload,
            source="RAZORPAY",
        )

        if result.get("status") == "error":
            _log.error("Razorpay webhook processing error: %s", result.get("reason"))

        # Blueprint Step 11: notify the merchant agent that payment verified.
        # Best-effort - never blocks the webhook ack.
        if (
            event_type == "payment.captured"
            and result.get("status") == "ok"
            and result.get("transaction_id")
        ):
            await _notify_merchant_agent(result["transaction_id"])

        return {"status": "ok", "event_id": event_id}

    except Exception as exc:
        _log.exception("Razorpay webhook handler error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"webhook_processing_error: {exc}",
        )
