"""Buyer Agent - AI agent that discovers merchants, requests quotes, and executes payments.

Phase 2: This agent represents the AI buyer in the A2A protocol.
It discovers merchant agents, requests quotes, accepts them, and executes payments.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from typing import Any

import httpx

from paari.a2a.protocol import serialize_message
from paari.a2a.types import A2AAction, A2AMessage, A2AResponse, A2AStatus

_log = logging.getLogger("paari.buyer_agent")


class BuyerAgent:
    """Buyer Agent handles purchasing for an end user.

    Key responsibilities:
    - Discover merchant agents via Paari
    - Request quotes for products
    - Accept quotes and initiate payment
    - Execute Razorpay payments
    - Handle payment results and order confirmation
    """

    def __init__(
        self,
        agent_id: str,
        paari_url: str = "http://localhost:8000",
        buyer_agent_id: str | None = None,
    ):
        self.agent_id = agent_id
        self.buyer_agent_id = buyer_agent_id or agent_id
        self.paari_url = paari_url.rstrip("/")
        self.http_client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.http_client:
            await self.http_client.aclose()

    async def discover_merchants(
        self,
        query: str | None = None,
        capabilities: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Discover active merchant agents.

        GET /api/agents/discover?agent_type=MERCHANT

        Returns:
            List of merchant agent cards
        """
        if not self.http_client:
            self.http_client = httpx.AsyncClient(timeout=30.0)

        params: dict[str, str] = {"agent_type": "MERCHANT"}
        if query:
            params["capabilities"] = ",".join(capabilities) if capabilities else query

        resp = await self.http_client.get(
            f"{self.paari_url}/api/agents/discover",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        return data.get("agents", [])

    async def request_quote(
        self,
        merchant_agent_id: str,
        product_id: str | None = None,
        product_name: str | None = None,
        quantity: int = 1,
        max_price_paise: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Request a quote from a merchant agent.

        Sends A2A REQUEST_QUOTE message to merchant agent.

        Returns:
            Quote details including quote_id, amount, expiry
        """
        if not self.http_client:
            self.http_client = httpx.AsyncClient(timeout=30.0)

        # Get merchant agent endpoint
        agent_card_resp = await self.http_client.get(
            f"{self.paari_url}/api/agents/{merchant_agent_id}",
        )
        if agent_card_resp.status_code == 404:
            raise ValueError(f"Merchant agent not found: {merchant_agent_id}")

        agent_card = agent_card_resp.json()
        merchant_endpoint = agent_card.get("a2a_endpoint")

        if not merchant_endpoint:
            # Fallback to Paari gateway
            merchant_endpoint = f"{self.paari_url}/a2a/merchant"

        message = A2AMessage(
            sender_id=self.agent_id,
            receiver_id=merchant_agent_id,
            action=A2AAction.REQUEST_QUOTE,
            payload={
                "product_id": product_id,
                "product_name": product_name,
                "quantity": quantity,
                "buyer_agent_id": self.buyer_agent_id,
                "max_price_paise": max_price_paise,
            },
            idempotency_key=idempotency_key or str(uuid.uuid4()),
        )

        resp = await self.http_client.post(
            merchant_endpoint,
            content=serialize_message(message),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()

        response = A2AResponse.model_validate(resp.json())

        if response.status == A2AStatus.ERROR:
            raise RuntimeError(f"Quote request failed: {response.error}")

        if response.status == A2AStatus.DENIED:
            raise PermissionError(f"Quote denied: {response.error}")

        return response.payload

    async def accept_quote(
        self,
        merchant_agent_id: str,
        quote_id: str,
        transaction_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Accept a quote and create payment session.

        Sends A2A ACCEPT_QUOTE message to merchant agent.

        Returns:
            Payment session details including session_id, authorized_amount
        """
        if not self.http_client:
            self.http_client = httpx.AsyncClient(timeout=30.0)

        # Get merchant agent endpoint
        agent_card_resp = await self.http_client.get(
            f"{self.paari_url}/api/agents/{merchant_agent_id}",
        )
        agent_card = agent_card_resp.json()
        merchant_endpoint = agent_card.get("a2a_endpoint") or f"{self.paari_url}/a2a/merchant"

        message = A2AMessage(
            sender_id=self.agent_id,
            receiver_id=merchant_agent_id,
            action=A2AAction.ACCEPT_QUOTE,
            payload={
                "quote_id": quote_id,
                "buyer_agent_id": self.buyer_agent_id,
                "transaction_id": transaction_id,
            },
            idempotency_key=idempotency_key or str(uuid.uuid4()),
        )

        resp = await self.http_client.post(
            merchant_endpoint,
            content=serialize_message(message),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()

        response = A2AResponse.model_validate(resp.json())

        if response.status == A2AStatus.ERROR:
            raise RuntimeError(f"Quote acceptance failed: {response.error}")

        if response.status == A2AStatus.DENIED:
            raise PermissionError(f"Quote acceptance denied: {response.error}")

        if response.status == A2AStatus.REVIEW_REQUIRED:
            return {
                **response.payload,
                "requires_review": True,
            }

        return response.payload

    async def execute_payment(
        self,
        payment_session_id: str,
        transaction_id: str | None = None,
        razorpay_order_id: str | None = None,
        amount_paise: int | None = None,
    ) -> dict[str, Any]:
        """Execute payment through Paari payment service.

        The agent NEVER owns Razorpay credentials and never executes the
        payment itself. It only requests a governed payment: Paari creates a
        bounded session/capability, then a server-side Razorpay order.

        - Stub mode: the capture is simulated via a signed payment.captured
          webhook so the demo completes without a browser.
        - Live mode: the agent returns the Razorpay order + checkout URL and
          STOPS. The human/UI completes Razorpay Checkout; Paari verifies the
          checkout signature and the real webhook, then fulfills.

        Returns:
            Stub: {"status": "VERIFIED", ...}.
            Live: {"status": "CHECKOUT_REQUIRED", transaction_id,
                   payment_session_id, razorpay_order_id, authorized_amount,
                   currency, checkout_url}.
        """
        from paari.config import settings

        if not self.http_client:
            self.http_client = httpx.AsyncClient(timeout=30.0)

        # Step 1: Create the Razorpay order for this payment session
        if not razorpay_order_id:
            if not transaction_id:
                # Fallback: the caller only knows a payment session id.
                # Authorize via /payments/create, then create the order.
                resp = await self.http_client.post(
                    f"{self.paari_url}/payments/create",
                    json={"transaction_id": payment_session_id},
                )
                resp.raise_for_status()
                payment_data = resp.json()

                if not payment_data.get("authorized"):
                    raise PermissionError(
                        f"Payment authorization failed: {payment_data.get('reason')}"
                    )

                transaction_id = payment_session_id
                amount_paise = amount_paise or payment_data.get("authorized_amount")
                checkout_session_id = payment_data.get("session_id") or payment_session_id
            else:
                checkout_session_id = payment_session_id

            resp = await self.http_client.post(
                f"{self.paari_url}/checkout/{transaction_id}/order",
                json={"session_id": checkout_session_id},
            )
            resp.raise_for_status()
            order_data = resp.json()
            razorpay_order_id = order_data.get("order_id")
            amount_paise = amount_paise or order_data.get("amount_paise")
            order_currency = order_data.get("currency") or "INR"
        else:
            order_currency = "INR"

        if not razorpay_order_id:
            raise RuntimeError("Payment order creation returned no order_id")

        # LIVE: the agent does not execute payment. Hand off to Razorpay
        # Checkout (human/UI completes it); Paari verifies the result.
        if settings.razorpay_mode == "live":
            return {
                "status": "CHECKOUT_REQUIRED",
                "transaction_id": transaction_id,
                "payment_session_id": payment_session_id,
                "razorpay_order_id": razorpay_order_id,
                "authorized_amount": amount_paise,
                "currency": order_currency,
                "checkout_url": f"{self.paari_url}/checkout/{transaction_id}",
            }

        # STUB: simulate the capture (demo) and deliver the signed webhook.
        # The webhook delivery uses Razorpay's real scheme: HMAC-SHA256 of the
        # raw body with the webhook secret — identical to Razorpay's servers.
        razorpay_payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        webhook_payload = {
            "event": "payment.captured",
            "id": f"evt_{uuid.uuid4().hex[:12]}",
            "payload": {
                "payment": {
                    "entity": {
                        "id": razorpay_payment_id,
                        "order_id": razorpay_order_id,
                        "amount": amount_paise,
                        "status": "captured",
                    }
                }
            },
        }
        import json as _json

        body = _json.dumps(webhook_payload).encode("utf-8")
        webhook_secret = (
            settings.razorpay_webhook_secret or "demo-webhook-secret"
        ).encode("utf-8")
        razorpay_signature = hmac.new(
            webhook_secret, body, hashlib.sha256
        ).hexdigest()

        # Step 3: Verify payment via webhook
        resp = await self.http_client.post(
            f"{self.paari_url}/webhooks/razorpay",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": razorpay_signature,
                "X-Razorpay-Event-Id": webhook_payload["id"],
            },
        )

        if resp.status_code == 200:
            return {
                "status": "VERIFIED",
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_order_id": razorpay_order_id,
                "amount_paise": amount_paise,
            }

        raise RuntimeError(f"Payment verification failed: {resp.text}")

    def _generate_signature(self, order_id: str, payment_id: str) -> str:
        """Generate HMAC signature for demo (in production, Razorpay signs this)."""
        import hashlib
        import hmac

        from paari.config import settings

        message = f"{order_id}|{payment_id}"
        secret = settings.razorpay_webhook_secret or "demo-webhook-secret"
        return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    async def send_message(
        self,
        receiver_id: str,
        action: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Send an A2A message through the Paari gateway.

        POST /a2a/merchant

        Returns:
            Response dict from the receiving agent.
        """
        if not self.http_client:
            self.http_client = httpx.AsyncClient(timeout=30.0)

        message = A2AMessage(
            sender_id=self.agent_id,
            receiver_id=receiver_id,
            action=A2AAction(action),
            payload=payload,
            idempotency_key=idempotency_key or str(uuid.uuid4()),
        )

        resp = await self.http_client.post(
            f"{self.paari_url}/a2a/merchant",
            content=serialize_message(message),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    async def verify_payment(
        self,
        transaction_id: str,
    ) -> dict[str, Any]:
        """Verify payment status for a transaction.

        GET /payments/transaction/{transaction_id}

        Returns:
            Transaction details with payment status
        """
        if not self.http_client:
            self.http_client = httpx.AsyncClient(timeout=30.0)

        resp = await self.http_client.get(
            f"{self.paari_url}/payments/transaction/{transaction_id}",
        )
        resp.raise_for_status()
        return resp.json()

    async def run_demo_purchase(
        self,
        product_name: str = "Nike Runner",
        quantity: int = 1,
        max_price_paise: int | None = None,
    ) -> dict[str, Any]:
        """Run a complete demo purchase flow.

        This demonstrates the full Phase 2 A2A purchase flow:
        1. Discover merchants
        2. Request quote
        3. Accept quote
        4. Execute payment
        5. Verify payment

        Returns:
            Complete purchase result with all details
        """
        results = {
            "steps": [],
            "success": False,
        }

        async with self:
            # Step 1: Discover merchants
            _log.info("Step 1: Discovering merchant agents...")
            merchants = await self.discover_merchants()
            if not merchants:
                results["error"] = "No merchant agents available"
                return results

            merchant = merchants[0]
            merchant_id = merchant["agent_id"]
            _log.info("Found merchant: %s", merchant.get("display_id", merchant_id))
            results["steps"].append({
                "step": "discover",
                "merchant_id": merchant_id,
                "status": "success",
            })

            # Step 2: Request quote
            _log.info("Step 2: Requesting quote for %s...", product_name)
            try:
                quote = await self.request_quote(
                    merchant_agent_id=merchant_id,
                    product_name=product_name,
                    quantity=quantity,
                    max_price_paise=max_price_paise,
                )
                _log.info("Quote received: %s", quote.get("quote_id"))
                results["steps"].append({
                    "step": "quote_request",
                    "quote_id": quote.get("quote_id"),
                    "amount_paise": quote.get("total_amount_paise"),
                    "status": "success",
                })
            except Exception as e:
                results["error"] = f"Quote request failed: {e}"
                results["steps"].append({
                    "step": "quote_request",
                    "status": "failed",
                    "error": str(e),
                })
                return results

            # Step 3: Accept quote
            _log.info("Step 3: Accepting quote %s...", quote.get("quote_id"))
            try:
                payment_session = await self.accept_quote(
                    merchant_agent_id=merchant_id,
                    quote_id=quote["quote_id"],
                    transaction_id=quote.get("transaction_id"),
                )
                _log.info("Payment session created: %s", payment_session.get("payment_session_id"))
                results["steps"].append({
                    "step": "quote_accept",
                    "payment_session_id": payment_session.get("payment_session_id"),
                    "status": "success",
                })
            except Exception as e:
                results["error"] = f"Quote acceptance failed: {e}"
                results["steps"].append({
                    "step": "quote_accept",
                    "status": "failed",
                    "error": str(e),
                })
                return results

            # Step 4: Execute payment
            _log.info("Step 4: Executing payment...")
            try:
                payment = await self.execute_payment(
                    payment_session_id=payment_session["payment_session_id"],
                    transaction_id=quote.get("transaction_id"),
                    razorpay_order_id=payment_session.get("razorpay_order_id"),
                    amount_paise=payment_session.get("authorized_amount"),
                )
                _log.info("Payment result: %s", payment.get("status"))
                if payment.get("status") == "CHECKOUT_REQUIRED":
                    # Live mode: agent hands off to Razorpay Checkout (human/UI
                    # completes the test payment; Paari verifies + fulfills).
                    results["steps"].append({
                        "step": "payment_execute",
                        "status": "CHECKOUT_REQUIRED",
                        "razorpay_order_id": payment.get("razorpay_order_id"),
                        "checkout_url": payment.get("checkout_url"),
                        "success": True,
                    })
                    results["checkout_required"] = True
                    results["checkout_url"] = payment.get("checkout_url")
                    results["transaction_id"] = quote.get("transaction_id")
                    results["quote_id"] = quote.get("quote_id")
                    return results
                results["steps"].append({
                    "step": "payment_execute",
                    "razorpay_payment_id": payment.get("razorpay_payment_id"),
                    "status": payment.get("status", "unknown"),
                    "success": True,
                })
            except Exception as e:
                results["error"] = f"Payment execution failed: {e}"
                results["steps"].append({
                    "step": "payment_execute",
                    "status": "failed",
                    "error": str(e),
                })
                return results

            results["success"] = True
            results["transaction_id"] = quote.get("transaction_id")
            results["quote_id"] = quote.get("quote_id")
            results["payment"] = payment

        return results
