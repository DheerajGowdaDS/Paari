"""Razorpay Live Adapter.

Uses the official razorpay Python client to interact with the Razorpay API.
Implements the same interface as the stub adapter for mode-agnostic usage.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

_log = logging.getLogger("paari.adapters.razorpay_live")


class RazorpayLiveAdapter:
    """Live Razorpay adapter using the razorpay Python client."""

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        webhook_secret: str,
    ) -> None:
        self.key_id = key_id
        self.key_secret = key_secret
        self.webhook_secret = webhook_secret
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        """Lazy-load the razorpay client."""
        if self._client is None:
            import razorpay

            self._client = razorpay.Client(
                auth=(self.key_id, self.key_secret),
                timeout=30,
            )
        return self._client

    async def create_order(
        self,
        amount_paise: int,
        currency: str = "INR",
        receipt: str | None = None,
        notes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a Razorpay order.

        Args:
            amount_paise: Amount in smallest currency unit (paise for INR).
            currency: Currency code (default: INR).
            receipt: Receipt ID for the order.
            notes: Optional notes dict.

        Returns:
            Razorpay order dict with id, amount, currency, status, etc.
        """
        try:
            order = self.client.order.create(
                {
                    "amount": amount_paise,
                    "currency": currency,
                    "receipt": receipt or None,
                    "notes": notes or {},
                }
            )
            _log.info("Created Razorpay order: %s", order.get("id"))
            return {
                "source": "razorpay",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "order_id": order.get("id"),
                "amount": order.get("amount"),
                "currency": order.get("currency"),
                "status": order.get("status"),
                "receipt": order.get("receipt"),
            }
        except Exception as exc:
            _log.error("Failed to create Razorpay order: %s", exc)
            raise

    async def verify_checkout_signature(
        self, order_id: str, payment_id: str, signature: str
    ) -> bool:
        """Verify a Razorpay checkout payment signature.

        Razorpay computes HMAC-SHA256(f"{order_id}|{payment_id}", key_secret).
        This is distinct from webhook-body verification below.
        """
        if not order_id or not payment_id or not signature or not self.key_secret:
            return False
        expected = hmac.new(
            self.key_secret.encode("utf-8"),
            f"{order_id}|{payment_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify the webhook signature.

        Args:
            payload: Raw request body bytes.
            signature: X-Razorpay-Signature header value.

        Returns:
            True if signature is valid, False otherwise.
        """
        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def generate_signature(self, payload: bytes) -> str:
        """Generate HMAC SHA256 signature for webhook simulation.

        Args:
            payload: JSON payload bytes.

        Returns:
            Hex digest of the HMAC SHA256 signature.
        """
        return hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

    async def charge_mandate(
        self, mandate_reference: str, amount_paise: int, currency: str = "INR"
    ) -> dict[str, Any]:
        """Charge a pre-authorized mandate via Razorpay.

        Live mandate/token product integration is pending verification
        against current Razorpay documentation; stub mode only for now.
        """
        raise NotImplementedError("live mandate charging is not yet integrated")

    async def verify_payment(self, payment_id: str, order_id: str) -> dict[str, Any]:
        """Fetch and verify a payment from Razorpay.

        Args:
            payment_id: Razorpay payment ID.
            order_id: Razorpay order ID.

        Returns:
            Payment entity dict with id, amount, status, order_id, etc.
        """
        try:
            payment = self.client.payment.fetch(payment_id)
            result = {
                "source": "razorpay",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "payment_id": payment.get("id"),
                "order_id": payment.get("order_id"),
                "amount": payment.get("amount"),
                "currency": payment.get("currency"),
                "status": payment.get("status"),
                "captured": payment.get("captured"),
            }
            if payment.get("order_id") != order_id:
                _log.warning(
                    "Order ID mismatch: expected %s, got %s", order_id, payment.get("order_id")
                )
                result["order_id_mismatch"] = True
            return result
        except Exception as exc:
            _log.error("Failed to fetch payment %s: %s", payment_id, exc)
            raise

    async def capture_payment(self, payment_id: str, amount_paise: int) -> dict[str, Any]:
        """Capture an authorized payment.

        Args:
            payment_id: Razorpay payment ID.
            amount_paise: Amount to capture in smallest unit.

        Returns:
            Updated payment entity.
        """
        try:
            captured = self.client.payment.capture(payment_id, amount_paise)
            _log.info("Captured payment: %s", payment_id)
            return {
                "source": "razorpay",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "payment_id": captured.get("id"),
                "amount": captured.get("amount"),
                "status": captured.get("status"),
                "captured": captured.get("captured"),
            }
        except Exception as exc:
            _log.error("Failed to capture payment %s: %s", payment_id, exc)
            raise


def get_razorpay_adapter() -> RazorpayLiveAdapter:
    """Factory to get a configured RazorpayLiveAdapter from settings."""
    from paari.config import settings

    return RazorpayLiveAdapter(
        key_id=settings.razorpay_key_id,
        key_secret=settings.razorpay_key_secret,
        webhook_secret=settings.razorpay_webhook_secret,
    )
