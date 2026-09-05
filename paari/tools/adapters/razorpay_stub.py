"""Razorpay adapter (stub).

Implements request_payment and a simulated webhook. The agent NEVER receives
VERIFIED directly — it only sees PENDING. Only a signed webhook event from
this adapter transitions payment state to VERIFIED, and that is what Paari
trusts. This is the payment-trust boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

# Demo webhook signing key (gitignored in production; here it's a fixture).
_WEBHOOK_SECRET = os.environ.get("PAARI_RAZORPAY_WEBHOOK_SECRET", "demo-webhook-secret")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _result(payload: dict[str, Any]) -> dict[str, Any]:
    return {"source": "razorpay", "fetched_at": _now(), **payload}


def request_payment(input, merchant_id: str) -> dict[str, Any]:
    """Request payment. The gateway persists the payment row; here we return
    the payment id and a PENDING state."""
    payment_id = str(uuid.uuid4())
    return _result(
        {
            "payment_id": payment_id,
            "state": "PENDING",
            "gateway_ref": f"MOCK-{payment_id[:8]}",
            "amount_paise": input.amount_paise,
            "currency": input.currency,
        }
    )


def sign_webhook(payload: dict[str, str]) -> str:
    """Sign a webhook payload with the demo HMAC secret."""
    import hashlib

    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        _WEBHOOK_SECRET.encode("ascii"), body.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_webhook_signature(payload: dict[str, str], signature: str) -> bool:
    """Verify a webhook signature. Returns True only if it matches."""
    expected = sign_webhook(payload)
    return hmac.compare_digest(expected, signature)


def build_verified_event(
    transaction_id: str, amount_paise: int, currency: str = "INR"
) -> dict[str, str]:
    """Build a VERIFIED webhook event for a transaction."""
    payload = {
        "event": "payment.authorized",
        "transaction_id": transaction_id,
        "amount_paise": str(amount_paise),
        "currency": currency,
        "timestamp": _now(),
    }
    payload["signature"] = sign_webhook(payload)
    return payload


class RazorpyStubAdapter:
    """Enhanced stub with verify_signature matching live adapter.

    Provides deterministic behavior for testing:
    - create_order: returns order_id with 'order_' prefix
    - simulate_payment: success for amounts ending in '00', failure for '99'
    """

    def __init__(self, webhook_secret: str = "") -> None:
        self.webhook_secret = webhook_secret or _WEBHOOK_SECRET

    def _sign_webhook(self, payload: dict[str, Any]) -> str:
        """Sign a webhook payload with the demo HMAC secret."""
        import hashlib

        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hmac.new(
            self.webhook_secret.encode("ascii"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def create_order(
        self,
        amount_paise: int,
        currency: str = "INR",
        receipt: str | None = None,
        notes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a deterministic stub order.

        Returns order_id with 'order_' prefix for easy identification.
        """
        order_id = f"order_{uuid.uuid4().hex[:12]}"
        return _result(
            {
                "order_id": order_id,
                "amount": amount_paise,
                "currency": currency,
                "status": "created",
                "receipt": receipt,
                "notes": notes or {},
            }
        )

    async def verify_checkout_signature(
        self, order_id: str, payment_id: str, signature: str
    ) -> bool:
        """Demo-only checkout signature check keyed on the webhook secret."""
        if not order_id or not payment_id or not signature:
            return False
        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            f"{order_id}|{payment_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify the webhook signature."""
        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def generate_signature(self, payload: bytes) -> str:
        """Generate HMAC SHA256 signature for webhook simulation."""
        return hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

    async def verify_payment(self, payment_id: str, order_id: str) -> dict[str, Any]:
        """Verify a payment (stub always returns success)."""
        return _result(
            {
                "payment_id": payment_id,
                "order_id": order_id,
                "status": "authorized",
                "captured": False,
            }
        )

    async def charge_mandate(
        self,
        mandate_reference: str,
        amount_paise: int,
        currency: str = "INR",
    ) -> dict[str, Any]:
        """Charge a pre-authorized mandate (deterministic stub).

        Approves amounts ending in '00', declines amounts ending in '99',
        mirroring simulate_payment semantics.
        """
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        if amount_paise % 100 == 99:
            return _result(
                {
                    "payment_id": payment_id,
                    "mandate_reference": mandate_reference,
                    "amount": amount_paise,
                    "currency": currency,
                    "status": "failed",
                    "success": False,
                }
            )
        return _result(
            {
                "payment_id": payment_id,
                "mandate_reference": mandate_reference,
                "amount": amount_paise,
                "currency": currency,
                "status": "captured",
                "success": True,
            }
        )

    async def simulate_payment(
        self,
        order_id: str,
        amount_paise: int,
    ) -> dict[str, Any]:
        """Simulate payment success/failure based on amount.

        Success: amounts ending in '00' (e.g., 479900 = ₹4,799.00)
        Failure: amounts ending in '99' (e.g., 479999 = ₹4,799.99 - 1paise)
        """
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        amount_last_two = amount_paise % 100

        if amount_last_two == 0:
            status = "captured"
            success = True
        elif amount_last_two == 99:
            status = "failed"
            success = False
        else:
            status = "captured"
            success = True

        return _result(
            {
                "payment_id": payment_id,
                "order_id": order_id,
                "amount": amount_paise,
                "status": status,
                "success": success,
            }
        )


def get_razorpay_stub_adapter() -> RazorpyStubAdapter:
    """Factory to get a configured RazorpyStubAdapter."""
    return RazorpyStubAdapter(webhook_secret=_WEBHOOK_SECRET)
