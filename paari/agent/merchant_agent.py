"""Merchant Agent - handles quote generation, negotiation, and order fulfillment.

Phase 2: This agent wraps Shopify tools and generates quotes based on
product + inventory + merchant policies. It communicates via A2A protocol.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from paari.a2a.protocol import (
    create_deny_response,
    create_error_response,
    create_review_response,
    create_success_response,
)
from paari.a2a.types import A2AAction, A2AMessage, A2AResponse, A2AStatus
from paari.config import settings
from paari.db.engine import get_session_maker
from paari.governance_engine.context import GovernanceContext, GovernanceLoadError
from paari.governance_engine.evaluator import get_governance_engine
from paari.governance_engine.state_machine import IllegalTransitionError, transition

_log = logging.getLogger("paari.merchant_agent")


class MerchantAgent:
    """Merchant Agent handles commerce operations for a merchant.

    Key responsibilities:
    - Product discovery and inventory checking
    - Quote generation based on product + policies
    - Deal negotiation (accept/reject/counter)
    - Order fulfillment after payment verification
    """

    def __init__(
        self,
        agent_id: str,
        merchant_id: str,
        governance_engine=None,
    ):
        self.agent_id = agent_id
        self.merchant_id = merchant_id
        self.governance_engine = governance_engine or get_governance_engine()

    async def handle_message(self, message: A2AMessage) -> A2AResponse:
        """Route A2A message to appropriate handler."""
        handlers = {
            A2AAction.REQUEST_QUOTE: self.handle_request_quote,
            A2AAction.ACCEPT_QUOTE: self.handle_accept_quote,
            A2AAction.NEGOTIATE: self.handle_negotiate,
            A2AAction.COUNTER_OFFER: self.handle_counter_offer,
            A2AAction.FULFILL_ORDER: self.handle_fulfill_order,
            A2AAction.PAYMENT_RESULT: self.handle_payment_result,
            A2AAction.DISCOVER: self.handle_discover,
        }

        handler = handlers.get(message.action)
        if handler is None:
            return create_error_response(
                message,
                f"Unknown action: {message.action}",
            )

        try:
            return await handler(message)
        except Exception as e:
            _log.exception("Error handling %s: %s", message.action, e)
            return create_error_response(message, str(e))

    async def handle_discover(self, message: A2AMessage) -> A2AResponse:
        """Handle DISCOVER action - return merchant capabilities."""
        payload = message.payload or {}

        maker = get_session_maker()
        async with maker() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT id, name, shopify_domain, status, policy_version, "
                        "avg_transaction_paise FROM merchants WHERE id = :id"
                    ),
                    {"id": self.merchant_id},
                )
            ).first()

        if not row:
            return create_deny_response(message, "Merchant not found")

        capabilities = [
            "catalog.search",
            "catalog.read",
            "inventory.read",
            "product.read",
            "quote.create",
            "deal.negotiate",
            "order.read",
            "order.create",
        ]

        return create_success_response(
            message,
            {
                "merchant_id": row.id,
                "merchant_name": row.name,
                "store_url": row.shopify_domain,
                "status": row.status,
                "capabilities": capabilities,
                "currency": "INR",
                "policies": {
                    "max_autonomous_transaction": settings.demo_merchant_autonomous_limit_paise,
                    "max_discount_percent": 10,
                    "max_quantity_per_line_item": 5,
                },
            },
        )

    async def handle_request_quote(self, message: A2AMessage) -> A2AResponse:
        """Handle REQUEST_QUOTE action - generate a quote.

        Payload:
        - product_id: Product SKU/ID
        - product_name: Product name for search
        - quantity: Number of items
        - buyer_agent_id: Requesting agent ID
        - max_price_paise: Maximum price buyer is willing to pay
        """
        payload = message.payload or {}
        product_id = payload.get("product_id") or payload.get("sku")
        product_name = payload.get("product_name")
        quantity = payload.get("quantity", 1)
        buyer_agent_id = payload.get("buyer_agent_id") or message.sender_id

        if not product_id and not product_name:
            return create_error_response(message, "product_id or product_name is required")

        # Get product info (mock for Phase 2 - in production would call Shopify)
        product_info = await self._get_product_info(product_id, product_name)

        if not product_info:
            return create_deny_response(message, "Product not found")

        # Calculate price
        base_price = product_info["price_paise"]
        max_price = payload.get("max_price_paise") or 0
        discount_pct = min(max_price / base_price if base_price > 0 else 0, 0.1)  # Max 10% discount
        final_price = int(base_price * (1 - discount_pct))
        total_amount = final_price * quantity

        # Create quote in DB
        quote_id = str(uuid.uuid4())
        tx_id = str(uuid.uuid4())
        display_id = f"QUOTE-{uuid.uuid4().hex[:8].upper()}"
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        auth_token = message.auth_token

        maker = get_session_maker()
        async with maker() as session:
            # Create transaction first
            await session.execute(
                text(
                    "INSERT INTO transactions (id, display_id, merchant_id, buyer_agent_id, "
                    " amount_paise, currency, state, policy_version, merchant_agent_id, buyer_credential_json) "
                    "VALUES (:id, :display_id, :merchant_id, :buyer, :amount, 'INR', "
                    " 'CREATED', 'v1', :ma_id, :cred)"
                ),
                {
                    "id": tx_id,
                    "display_id": f"TXN-{uuid.uuid4().hex[:8].upper()}",
                    "merchant_id": self.merchant_id,
                    "buyer": buyer_agent_id,
                    "amount": total_amount,
                    "ma_id": self.agent_id,
                    "cred": auth_token,
                },
            )

            # Create quote (carry the agreed product SKU + quantity so the
            # order built later matches the quoted line — blueprint Step 12)
            await session.execute(
                text(
                    "INSERT INTO quotes (id, transaction_id, merchant_id, product_sku, quantity, "
                    " amount_paise, expires_at, state) "
                    "VALUES (:id, :tx_id, :merchant_id, :sku, :qty, :amount, :expires_at, 'PENDING')"
                ),
                {
                    "id": quote_id,
                    "tx_id": tx_id,
                    "merchant_id": self.merchant_id,
                    "sku": product_info.get("id"),
                    "qty": int(quantity),
                    "amount": total_amount,
                    "expires_at": expires_at.isoformat(),
                },
            )

            # Link the quote to the transaction (QUOTE_VALIDATION requires it)
            await session.execute(
                text("UPDATE transactions SET quote_id = :qid WHERE id = :tid"),
                {"qid": quote_id, "tid": tx_id},
            )
            await session.commit()

        return create_success_response(
            message,
            {
                "quote_id": quote_id,
                "transaction_id": tx_id,
                "display_id": display_id,
                "product_id": product_info["id"],
                "product_name": product_info["name"],
                "quantity": quantity,
                "unit_price_paise": final_price,
                "total_amount_paise": total_amount,
                "currency": "INR",
                "expires_at": expires_at.isoformat(),
                "state": "PENDING",
                "merchant_agent_id": self.agent_id,
                "buyer_agent_id": buyer_agent_id,
                "line_items": [
                    {
                        "product_id": product_info["id"],
                        "product_name": product_info["name"],
                        "quantity": quantity,
                        "unit_price_paise": final_price,
                        "total_price_paise": total_amount,
                    }
                ],
            },
        )

    async def handle_accept_quote(self, message: A2AMessage) -> A2AResponse:
        """Handle ACCEPT_QUOTE action - accept quote and create payment session.

        Payload:
        - quote_id: Quote to accept
        - buyer_agent_id: Buyer agent ID
        - transaction_id: Optional pre-created transaction
        """
        payload = message.payload or {}
        quote_id = payload.get("quote_id")
        buyer_agent_id = payload.get("buyer_agent_id") or message.sender_id
        auth_token = message.auth_token

        if not quote_id:
            return create_error_response(message, "quote_id is required")

        maker = get_session_maker()
        async with maker() as session:
            # Get quote
            quote_row = (
                await session.execute(
                    text(
                        "SELECT id, transaction_id, amount_paise, state, expires_at "
                        "FROM quotes WHERE id = :id"
                    ),
                    {"id": quote_id},
                )
            ).first()

            if not quote_row:
                return create_deny_response(message, "Quote not found")

            if quote_row.state == "ACCEPTED":
                return create_deny_response(message, "Quote already accepted")

            if quote_row.state == "EXPIRED":
                return create_deny_response(message, "Quote has expired")

            # Check expiry
            expires_at = datetime.fromisoformat(quote_row.expires_at)
            if datetime.now(UTC) > expires_at:
                await session.execute(
                    text("UPDATE quotes SET state = 'EXPIRED' WHERE id = :id"),
                    {"id": quote_id},
                )
                await session.commit()
                return create_deny_response(message, "Quote has expired")

            tx_id = quote_row.transaction_id

            # Transition quote to ACCEPTED
            await session.execute(
                text("UPDATE quotes SET state = 'ACCEPTED' WHERE id = :id"),
                {"id": quote_id},
            )

            # Move the transaction into governance evaluation state
            # (CREATED -> GOVERNANCE_PENDING; already-governed txs skip)
            try:
                await transition(session, tx_id, "GOVERNANCE_PENDING")
            except IllegalTransitionError:
                pass

            # Store buyer credential (auth_token) on the transaction if provided
            if auth_token:
                await session.execute(
                    text("UPDATE transactions SET buyer_credential_json = :cred WHERE id = :tid"),
                    {"cred": auth_token, "tid": tx_id},
                )

            # Commit pre-evaluation writes so the evaluator's audit writes
            # (separate connection) don't hit a SQLite write lock.
            await session.commit()

            # Run governance evaluation (transitions to AUTHORIZED/DENIED/REVIEW_REQUIRED)
            try:
                ctx = await GovernanceContext.load(session, tx_id, message.message_id)
            except GovernanceLoadError as exc:
                return create_deny_response(message, f"Governance error: {exc}")

            decision = await self.governance_engine.evaluate(ctx, session)
            await session.commit()

            if decision.decision == "DENY":
                failed_reasons = [f"{c.check}: {c.reason_code}" for c in decision.failed_checks]
                return create_deny_response(
                    message,
                    f"Governance denied: {', '.join(failed_reasons)}",
                )

            if decision.decision == "REVIEW":
                return create_review_response(
                    message,
                    {"quote_id": quote_id, "transaction_id": tx_id},
                    reason=f"Review required: {[c.reason_code for c in decision.review_checks]}",
                )

            # ALLOW - create payment session + one-time capability
            session_id = str(uuid.uuid4())
            session_display_id = f"PS-{uuid.uuid4().hex[:8].upper()}"
            cap_id = str(uuid.uuid4())
            cap_display_id = f"CAP-{uuid.uuid4().hex[:8].upper()}"
            expires_at = datetime.now(UTC) + timedelta(minutes=10)

            await session.execute(
                text(
                    "INSERT INTO payment_sessions (id, display_id, transaction_id, "
                    " authorized_amount, currency, status, expires_at) "
                    "VALUES (:id, :display_id, :tx_id, :amount, 'INR', 'ACTIVE', :expires)"
                ),
                {
                    "id": session_id,
                    "display_id": session_display_id,
                    "tx_id": tx_id,
                    "amount": quote_row.amount_paise,
                    "expires": expires_at.isoformat(),
                },
            )

            # Create one-time capability
            await session.execute(
                text(
                    "INSERT INTO payment_capabilities (id, display_id, transaction_id, "
                    " action, max_amount, usage, used) "
                    "VALUES (:id, :display_id, :tx_id, 'payment.execute', :max, 'ONE_TIME', 0)"
                ),
                {
                    "id": cap_id,
                    "display_id": cap_display_id,
                    "tx_id": tx_id,
                    "max": quote_row.amount_paise,
                },
            )

            # Transaction moves to PAYMENT_PENDING (AUTHORIZED -> PAYMENT_PENDING)
            try:
                await transition(session, tx_id, "PAYMENT_PENDING")
            except IllegalTransitionError:
                pass

            await session.commit()

            return create_success_response(
                message,
                {
                    "quote_id": quote_id,
                    "transaction_id": tx_id,
                    "payment_session_id": session_id,
                    "payment_session_display_id": session_display_id,
                    "capability_id": cap_id,
                    "capability_display_id": cap_display_id,
                    "authorized_amount": quote_row.amount_paise,
                    "currency": "INR",
                    "expires_at": expires_at.isoformat(),
                    "status": "AUTHORIZED",
                    "razorpay_key_id": settings.razorpay_key_id or "rzp_test_XXXXX",
                },
            )

    async def handle_payment_result(self, message: A2AMessage) -> A2AResponse:
        """Handle PAYMENT_RESULT action - Paari notifies merchant that payment verified.

        Blueprint Step 11: Paari pushes {transaction_id, payment_status: VERIFIED,
        next_action: FULFILL} so the merchant agent knows it can continue.

        Payload:
        - transaction_id: Transaction that was paid
        - payment_status: Payment result (e.g. VERIFIED)
        - next_action: What the merchant should do next (e.g. FULFILL)
        """
        payload = message.payload or {}
        transaction_id = payload.get("transaction_id")

        if not transaction_id:
            return create_error_response(message, "transaction_id is required")

        maker = get_session_maker()
        async with maker() as session:
            tx_row = (
                await session.execute(
                    text("SELECT id, state FROM transactions WHERE id = :id"),
                    {"id": transaction_id},
                )
            ).first()

            if not tx_row:
                return create_deny_response(message, "Transaction not found")

        _log.info(
            "Payment result for tx %s: %s (next: %s)",
            transaction_id,
            payload.get("payment_status", "VERIFIED"),
            payload.get("next_action", "FULFILL"),
        )

        return create_success_response(
            message,
            {
                "transaction_id": transaction_id,
                "payment_status": payload.get("payment_status", "VERIFIED"),
                "next_action": payload.get("next_action", "FULFILL"),
                "received": True,
            },
        )

    async def handle_negotiate(self, message: A2AMessage) -> A2AResponse:
        """Handle NEGOTIATE action - buyer proposes counter terms."""
        payload = message.payload or {}
        quote_id = payload.get("quote_id")
        counter_amount = payload.get("counter_amount_paise")

        if not quote_id or not counter_amount:
            return create_error_response(
                message,
                "quote_id and counter_amount_paise are required",
            )

        maker = get_session_maker()
        async with maker() as session:
            quote_row = (
                await session.execute(
                    text("SELECT amount_paise, state FROM quotes WHERE id = :id"),
                    {"id": quote_id},
                )
            ).first()

        if not quote_row:
            return create_deny_response(message, "Quote not found")

        # Reject if quote already accepted
        if quote_row.state == "ACCEPTED":
            return create_deny_response(message, "Quote already accepted")

        # Accept counter if within 10% of original
        original = quote_row.amount_paise
        if counter_amount >= original * 0.9:
            return create_success_response(
                message,
                {
                    "quote_id": quote_id,
                    "counter_amount_paise": counter_amount,
                    "status": "COUNTER_ACCEPTED",
                    "message": "Counter offer accepted",
                },
            )

        return create_success_response(
            message,
            {
                "quote_id": quote_id,
                "counter_amount_paise": counter_amount,
                "original_amount_paise": original,
                "status": "COUNTER_REJECTED",
                "message": "Counter offer rejected - price too low",
                "min_acceptable_paise": int(original * 0.9),
            },
        )

    async def handle_counter_offer(self, message: A2AMessage) -> A2AResponse:
        """Handle COUNTER_OFFER action - merchant proposes new terms."""
        # Similar to negotiate but from merchant side
        return await self.handle_negotiate(message)

    async def handle_fulfill_order(self, message: A2AMessage) -> A2AResponse:
        """Handle FULFILL_ORDER action - fulfill after payment verification.

        Payload:
        - transaction_id: Transaction to fulfill
        - order_id: Shopify order ID (optional)
        - tracking_number: Shipping tracking (optional)
        - carrier: Shipping carrier (optional)
        """
        payload = message.payload or {}
        transaction_id = payload.get("transaction_id")

        if not transaction_id:
            return create_error_response(message, "transaction_id is required")

        maker = get_session_maker()
        async with maker() as session:
            # Verify transaction is paid
            tx_row = (
                await session.execute(
                    text(
                        "SELECT state, razorpay_payment_id, amount_paise "
                        "FROM transactions WHERE id = :id"
                    ),
                    {"id": transaction_id},
                )
            ).first()

            if not tx_row:
                return create_deny_response(message, "Transaction not found")

            if tx_row.state != "PAYMENT_VERIFIED":
                return create_deny_response(
                    message,
                    f"Transaction not ready for fulfillment. State: {tx_row.state}",
                )

            # Get the accepted quote to pass into the adapter
            quote_row = (
                await session.execute(
                    text(
                        "SELECT id, amount_paise FROM quotes "
                        "WHERE transaction_id = :tid AND state = 'ACCEPTED' LIMIT 1"
                    ),
                    {"tid": transaction_id},
                )
            ).first()

            # Create Shopify order via the configured adapter (stub or live)
            from paari.adapters.commerce import get_commerce_adapter

            adapter = get_commerce_adapter()
            order_result = await adapter.confirm_order(
                transaction_id=transaction_id,
                quote_id=quote_row.id if quote_row else None,
            )

            if order_result and order_result.get("error"):
                # Blueprint Step 14: payment verified but Shopify failed ->
                # FULFILLMENT_PENDING (retry/reconciliation), not a silent stall.
                try:
                    await transition(session, transaction_id, "FULFILLMENT_PENDING")
                except IllegalTransitionError:
                    pass
                await session.commit()
                return create_error_response(
                    message,
                    f"Order creation failed: {order_result['error']}",
                )

            order_id = order_result.get("order_id") if order_result else None
            if not order_id:
                order_id = payload.get("order_id") or f"SHOPIFY-{uuid.uuid4().hex[:8].upper()}"

            # Walk PAYMENT_VERIFIED -> ORDER_CONFIRMED -> COMPLETED via the
            # state machine (blueprint Steps 12-13: order created then confirmed).
            try:
                await transition(session, transaction_id, "ORDER_CONFIRMED")
            except IllegalTransitionError:
                pass
            try:
                await transition(session, transaction_id, "COMPLETED")
            except IllegalTransitionError:
                pass

            await session.commit()

            return A2AResponse(
                message_id=message.message_id,
                sender_id=message.receiver_id,
                receiver_id=message.sender_id,
                status=A2AStatus.ORDER_CONFIRMED,
                payload={
                    "transaction_id": transaction_id,
                    "order_id": order_id,
                    "fulfillment_status": "FULFILLED",
                    "state": "ORDER_CONFIRMED",
                    "tracking_number": payload.get("tracking_number"),
                    "carrier": payload.get("carrier"),
                    "amount_paise": tx_row.amount_paise,
                    "message": "Order fulfilled successfully",
                },
                error=None,
            )

    async def _get_product_info(
        self, product_id: str | None, product_name: str | None
    ) -> dict | None:
        """Get product info from the configured Shopify adapter (stub or live)."""
        from paari.adapters.commerce import get_commerce_adapter

        adapter = get_commerce_adapter()

        # Search by SKU/product id
        if product_id:
            result = await adapter.get_product(product_id)
            if result and not result.get("error"):
                product = result.get("product", {})
                inventory_result = await adapter.get_inventory(product_id)
                return {
                    "id": product_id,
                    "name": product.get("name", "Unknown"),
                    "price_paise": product.get("price_paise", 0),
                    "inventory": inventory_result.get("available", 0) if inventory_result else 0,
                }

        # Search by name
        if product_name:
            search_result = await adapter.search_products(product_name, limit=5)
            products = search_result.get("products", [])
            if products:
                product = products[0]
                sku = product.get("sku") or product.get("id")
                inventory_result = await adapter.get_inventory(sku)
                return {
                    "id": sku,
                    "name": product.get("name", product_name),
                    "price_paise": product.get("price_paise", 0),
                    "inventory": inventory_result.get("available", 0) if inventory_result else 0,
                }

        return None


def get_merchant_agent(agent_id: str = "MA-001") -> MerchantAgent:
    """Get a MerchantAgent instance for the given agent ID."""
    return MerchantAgent(
        agent_id=agent_id,
        merchant_id="MER-001",
    )
