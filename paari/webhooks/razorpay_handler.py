"""Razorpay webhook event handler.

Handles:
- payment.captured — Payment successfully captured
- payment.failed — Payment failed
- order.paid — Order paid (authorized)

Dedup: Uses webhook_events table with UNIQUE constraint on event_id.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from sqlalchemy import text

from paari.db.engine import get_session_maker
from paari.webhooks.queue import WebhookEvent

_log = logging.getLogger("paari.webhooks.razorpay")


async def handle_payment_captured(event: dict[str, Any]) -> dict[str, Any]:
    """Handle payment.captured event.

    Updates transaction to PAYMENT_VERIFIED and marks payment session as COMPLETED.
    """
    maker = get_session_maker()
    async with maker() as session:
        payment_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = payment_entity.get("id")
        order_id = payment_entity.get("order_id")
        amount = payment_entity.get("amount")

        if not order_id:
            _log.warning("payment.captured missing order_id")
            return {"status": "error", "reason": "missing_order_id"}

        tx_row = (
            await session.execute(
                text("SELECT id, state FROM transactions WHERE razorpay_order_id = :oid"),
                {"oid": order_id},
            )
        ).first()

        if tx_row is None:
            _log.warning("Transaction not found for order: %s", order_id)
            return {"status": "error", "reason": "transaction_not_found"}

        tx_id = tx_row.id

        if tx_row.state in (
            "PAYMENT_VERIFIED",
            "FULFILLMENT_PENDING",
            "ORDER_CONFIRMED",
            "COMPLETED",
        ):
            _log.info("Transaction %s already verified/settled (state=%s), skipping", tx_id, tx_row.state)
            return {
                "status": "ok",
                "already_verified": True,
                "already_processed": True,
                "transaction_id": tx_id,
            }

        await session.execute(
            text(
                "UPDATE transactions SET razorpay_payment_id = :pid, state = 'PAYMENT_VERIFIED' "
                "WHERE id = :tid"
            ),
            {"pid": payment_id, "tid": tx_id},
        )

        await session.execute(
            text(
                "UPDATE payment_sessions SET status = 'COMPLETED' "
                "WHERE transaction_id = :tid AND status = 'ACTIVE'"
            ),
            {"tid": tx_id},
        )

        await session.commit()

        _log.info(
            "Payment captured: tx=%s payment=%s order=%s amount=%s",
            tx_id,
            payment_id,
            order_id,
            amount,
        )

        return {
            "status": "ok",
            "transaction_id": tx_id,
            "payment_id": payment_id,
            "order_id": order_id,
        }


async def handle_payment_failed(event: dict[str, Any]) -> dict[str, Any]:
    """Handle payment.failed event.

    Updates transaction to PAYMENT_FAILED.
    """
    maker = get_session_maker()
    async with maker() as session:
        payment_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = payment_entity.get("id")
        order_id = payment_entity.get("order_id")

        if not order_id:
            _log.warning("payment.failed missing order_id")
            return {"status": "error", "reason": "missing_order_id"}

        tx_row = (
            await session.execute(
                text("SELECT id, state FROM transactions WHERE razorpay_order_id = :oid"),
                {"oid": order_id},
            )
        ).first()

        if tx_row is None:
            _log.warning("Transaction not found for order: %s", order_id)
            return {"status": "error", "reason": "transaction_not_found"}

        tx_id = tx_row.id

        if tx_row.state in (
            "PAYMENT_VERIFIED",
            "FULFILLMENT_PENDING",
            "ORDER_CONFIRMED",
            "COMPLETED",
        ):
            _log.info("Transaction %s already verified/settled (state=%s), ignoring late payment.failed", tx_id, tx_row.state)
            return {
                "status": "ok",
                "already_verified": True,
                "already_processed": True,
                "transaction_id": tx_id,
            }

        await session.execute(
            text(
                "UPDATE transactions SET razorpay_payment_id = :pid, state = 'PAYMENT_FAILED' WHERE id = :tid"
            ),
            {"pid": payment_id, "tid": tx_id},
        )

        await session.commit()

        _log.info("Payment failed: tx=%s payment=%s order=%s", tx_id, payment_id, order_id)

        return {
            "status": "ok",
            "transaction_id": tx_id,
            "payment_id": payment_id,
        }


async def handle_order_paid(event: dict[str, Any]) -> dict[str, Any]:
    """Handle order.paid event.

    This is fired when an order is paid (authorized but not captured).
    Similar to payment.captured but for the order-level event.
    """
    maker = get_session_maker()
    async with maker() as session:
        order_entity = event.get("payload", {}).get("order", {}).get("entity", {})
        order_id = order_entity.get("id")
        amount = order_entity.get("amount")

        if not order_id:
            _log.warning("order.paid missing order_id")
            return {"status": "error", "reason": "missing_order_id"}

        tx_row = (
            await session.execute(
                text("SELECT id, state FROM transactions WHERE razorpay_order_id = :oid"),
                {"oid": order_id},
            )
        ).first()

        if tx_row is None:
            _log.warning("Transaction not found for order: %s", order_id)
            return {"status": "error", "reason": "transaction_not_found"}

        tx_id = tx_row.id

        if tx_row.state in ("PAYMENT_VERIFIED", "ORDER_CONFIRMED", "COMPLETED"):
            _log.info("Transaction %s already in state %s, skipping", tx_id, tx_row.state)
            return {"status": "ok", "already_processed": True}

        await session.execute(
            text("UPDATE transactions SET state = 'PAYMENT_VERIFIED' WHERE id = :tid"),
            {"tid": tx_id},
        )

        await session.commit()

        _log.info("Order paid: tx=%s order=%s amount=%s", tx_id, order_id, amount)

        return {
            "status": "ok",
            "transaction_id": tx_id,
            "order_id": order_id,
        }


async def handle_razorpay_event(event: dict[str, Any]) -> dict[str, Any]:
    """Main entry point for Razorpay webhook events.

    Routes to the appropriate handler based on event type.

    Args:
        event: Parsed webhook event dict.

    Returns:
        Result dict with status and details.
    """
    event_type = event.get("event", "")
    event_id = event.get("id", "")

    _log.info("Processing Razorpay event: type=%s id=%s", event_type, event_id)

    handler_map = {
        "payment.captured": handle_payment_captured,
        "payment.failed": handle_payment_failed,
        "order.paid": handle_order_paid,
    }

    handler = handler_map.get(event_type)
    if handler is None:
        _log.warning("No handler for Razorpay event type: %s", event_type)
        return {"status": "skipped", "reason": f"no_handler_for_{event_type}"}

    try:
        result = await handler(event)
    except Exception as exc:
        _log.error("Handler error for %s: %s", event_type, exc)
        return {"status": "error", "reason": str(exc)}

    if (
        event_type in ("payment.captured", "order.paid")
        and result.get("status") == "ok"
        and result.get("transaction_id")
        and not event.get("synthetic")
    ):
        try:
            from paari.payment.settle import settle_verified_transaction

            settle = await settle_verified_transaction(result["transaction_id"])
            result["settled"] = settle.get("fulfilled", False)
            if not settle.get("fulfilled"):
                result["settle_reason"] = settle.get("reason")
        except Exception as exc:
            _log.warning("Post-verification settle failed: %s", exc)
    return result


async def persist_and_process_razorpay_webhook(
    event_type: str,
    event_id: str,
    payload: dict[str, Any],
    source: str = "RAZORPAY",
) -> dict[str, Any]:
    """Persist Razorpay webhook event and process it.

    Uses webhook_events table for dedup via UNIQUE constraint on event_id.

    Args:
        event_type: Event type (e.g., 'payment.captured').
        event_id: Unique event ID from Razorpay.
        payload: Full event payload.
        source: Source identifier (default: RAZORPAY).

    Returns:
        Result dict with status and details.
    """
    maker = get_session_maker()
    async with maker() as session:
        webhook_event_id = secrets.token_hex(16)

        try:
            await session.execute(
                text(
                    "INSERT INTO webhook_events (id, event_id, source, topic, webhook_id, payload_json, status) "
                    "VALUES (:id, :eid, :source, :topic, :wid, :payload, 'PENDING')"
                ),
                {
                    "id": webhook_event_id,
                    "eid": event_id,
                    "source": source,
                    "topic": event_type,
                    "wid": event_id,
                    "payload": json.dumps(payload),
                },
            )
            await session.commit()
        except Exception as exc:
            if "UNIQUE constraint" in str(exc) or "Duplicate" in str(exc):
                _log.info("Duplicate webhook event: %s", event_id)
                return {"status": "ok", "note": "duplicate_event"}
            raise

    event_dict = {
        "event": event_type,
        "id": event_id,
        "payload": payload,
    }

    return await handle_razorpay_event(event_dict)
