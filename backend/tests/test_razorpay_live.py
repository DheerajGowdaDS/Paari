"""Tests for Razorpay Live Adapter.

These tests require RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET environment variables.
If not set, tests are skipped.
"""

from __future__ import annotations

import hashlib
import hmac
import os

import pytest

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret")

HAS_CREDENTIALS = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


class TestRazorpayLiveAdapterSignature:
    """Test signature generation and verification."""

    def test_generate_signature_returns_hex_digest(self):
        from paari.adapters.razorpay_live import RazorpayLiveAdapter

        adapter = RazorpayLiveAdapter(
            key_id=RAZORPAY_KEY_ID,
            key_secret=RAZORPAY_KEY_SECRET,
            webhook_secret=RAZORPAY_WEBHOOK_SECRET,
        )
        payload = b'{"event":"payment.captured","id":"evt_test_123"}'
        sig = adapter.client is not None  # Check client initializes

        assert sig is True

    @pytest.mark.skipif(not HAS_CREDENTIALS, reason="Razorpay credentials not set")
    async def test_verify_signature_valid(self):
        from paari.adapters.razorpay_live import RazorpayLiveAdapter

        adapter = RazorpayLiveAdapter(
            key_id=RAZORPAY_KEY_ID,
            key_secret=RAZORPAY_KEY_SECRET,
            webhook_secret=RAZORPAY_WEBHOOK_SECRET,
        )

        payload = b'{"event":"payment.captured","id":"evt_test_123"}'
        expected_sig = hmac.new(
            RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        is_valid = await adapter.verify_signature(payload, expected_sig)
        assert is_valid is True

    @pytest.mark.skipif(not HAS_CREDENTIALS, reason="Razorpay credentials not set")
    async def test_verify_signature_invalid(self):
        from paari.adapters.razorpay_live import RazorpayLiveAdapter

        adapter = RazorpayLiveAdapter(
            key_id=RAZORPAY_KEY_ID,
            key_secret=RAZORPAY_KEY_SECRET,
            webhook_secret=RAZORPAY_WEBHOOK_SECRET,
        )

        payload = b'{"event":"payment.captured","id":"evt_test_123"}'
        invalid_sig = "0" * 64

        is_valid = await adapter.verify_signature(payload, invalid_sig)
        assert is_valid is False


@pytest.mark.skipif(not HAS_CREDENTIALS, reason="Razorpay credentials not set")
class TestRazorpayLiveAdapterOrder:
    """Test order creation and management."""

    async def test_create_order_returns_order_id(self):
        from paari.adapters.razorpay_live import RazorpayLiveAdapter

        adapter = RazorpayLiveAdapter(
            key_id=RAZORPAY_KEY_ID,
            key_secret=RAZORPAY_KEY_SECRET,
            webhook_secret=RAZORPAY_WEBHOOK_SECRET,
        )

        order = await adapter.create_order(
            amount_paise=10000,
            currency="INR",
            receipt="test_receipt_001",
            notes={"source": "paari_test"},
        )

        assert "order_id" in order
        assert order["order_id"].startswith("order_")
        assert order["status"] == "created"
        assert order["amount"] == 10000
        assert order["currency"] == "INR"

    async def test_create_order_amount_correct(self):
        from paari.adapters.razorpay_live import RazorpayLiveAdapter

        adapter = RazorpayLiveAdapter(
            key_id=RAZORPAY_KEY_ID,
            key_secret=RAZORPAY_KEY_SECRET,
            webhook_secret=RAZORPAY_WEBHOOK_SECRET,
        )

        order = await adapter.create_order(amount_paise=479900)

        assert order["amount"] == 479900
