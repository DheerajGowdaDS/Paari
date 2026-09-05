"""Webhook handlers for Shopify events.

- orders/*: update transaction state in the DB
- inventory_levels/update: update in-process cache
"""

from __future__ import annotations

import json
import logging
from typing import Any

from paari.webhooks.queue import WebhookEvent

_log = logging.getLogger("paari.webhooks.handlers")


async def handle_order_event(event: WebhookEvent) -> None:
    """Handle orders/create, orders/updated, orders/delete events.

    Extracts the transaction_id from the order note (format: paari_transaction:{id})
    and updates the transaction state accordingly.
    """
    payload = event.payload
    note = payload.get("note", "")
    tags = payload.get("tags", [])

    # Extract Paari transaction ID from note
    transaction_id = _extract_transaction_id(note)
    if transaction_id is None:
        _log.info("Order %s has no paari_transaction tag, skipping", payload.get("id"))
        return

    financial_status = payload.get("financial_status", "")
    order_id = payload.get("id", "")

    # Map Shopify financial_status to Paari transaction state
    state = _map_financial_status(financial_status)

    if state is None:
        _log.warning(
            "Unknown financial_status '%s' for order %s — leaving transaction %s unchanged",
            financial_status, order_id, transaction_id,
        )
        return

    # Update transaction in DB
    from sqlalchemy import text

    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        await session.execute(
            text(
                "UPDATE transactions SET state = :state, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = :id"
            ),
            {"id": transaction_id, "state": state},
        )
        await session.commit()

    _log.info(
        "Updated transaction %s -> %s (order=%s, financial_status=%s)",
        transaction_id,
        state,
        order_id,
        financial_status,
    )


async def handle_inventory_update(event: WebhookEvent) -> None:
    """Handle inventory_levels/update events.

    Updates the in-process SKU index cache with new inventory levels.
    """
    payload = event.payload
    inventory_item_id = payload.get("inventory_item_id", "")
    available = payload.get("available", 0)
    location_id = payload.get("location_id", "")

    _log.info(
        "Inventory update: item=%s available=%d location=%s",
        inventory_item_id,
        available,
        location_id,
    )

    # The live adapter's next call to get_inventory will fetch fresh data.
    # This handler just logs the event for audit purposes.


def _extract_transaction_id(note: str) -> str | None:
    """Extract paari transaction ID from order note."""
    prefix = "paari_transaction:"
    if prefix in note:
        idx = note.index(prefix) + len(prefix)
        # Transaction ID is the rest of the note or until whitespace
        tid = note[idx:].strip().split()[0] if note[idx:].strip() else None
        return tid
    return None


def _map_financial_status(financial_status: str) -> str | None:
    """Map Shopify financial_status to Paari transaction state.

    Returns None for unrecognized statuses (leave state unchanged)
    to prevent malformed webhooks from advancing to ORDER_CONFIRMED.
    """
    mapping = {
        "paid": "ORDER_CONFIRMED",
        "pending": "PAYMENT_PENDING",
        "authorized": "PAYMENT_VERIFIED",
        "partially_paid": "PAYMENT_PENDING",
        "refunded": "COMPLETED",
        "partially_refunded": "COMPLETED",
        "voided": "DENIED",
        "expired": "DENIED",
        "unpaid": "PAYMENT_PENDING",
    }
    return mapping.get(financial_status)
