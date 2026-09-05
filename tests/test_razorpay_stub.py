"""Tests for Razorpay Stub Adapter."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from paari.tools.adapters.razorpay_stub import RazorpyStubAdapter, get_razorpay_stub_adapter


class TestRazorpyStubAdapterCreateOrder:
    """Test stub order creation."""

    @pytest.mark.anyio
    async def test_create_order_returns_order_with_prefix(self):
        adapter = RazorpyStubAdapter(webhook_secret="test_secret")
        order = await adapter.create_order(amount_paise=10000, currency="INR")

        assert "order_id" in order
        assert order["order_id"].startswith("order_")
        assert order["status"] == "created"
        assert order["amount"] == 10000

    @pytest.mark.anyio
    async def test_create_order_preserves_amount(self):
        adapter = RazorpyStubAdapter()
        order = await adapter.create_order(amount_paise=479900)

        assert order["amount"] == 479900

    @pytest.mark.anyio
    async def test_create_order_includes_receipt(self):
        adapter = RazorpyStubAdapter()
        order = await adapter.create_order(amount_paise=10000, receipt="rcpt_001")

        assert order["receipt"] == "rcpt_001"

    @pytest.mark.anyio
    async def test_create_order_includes_notes(self):
        adapter = RazorpyStubAdapter()
        notes = {"source": "test", "transaction_id": "tx_123"}
        order = await adapter.create_order(amount_paise=10000, notes=notes)

        assert order["notes"]["source"] == "test"
        assert order["notes"]["transaction_id"] == "tx_123"


class TestRazorpyStubAdapterSignature:
    """Test signature generation and verification."""

    @pytest.mark.anyio
    async def test_generate_signature_returns_hex(self):
        adapter = RazorpyStubAdapter(webhook_secret="test_secret")
        payload = b'{"event":"payment.captured","id":"evt_test"}'

        sig = await adapter.generate_signature(payload)

        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    @pytest.mark.anyio
    async def test_verify_signature_valid(self):
        adapter = RazorpyStubAdapter(webhook_secret="test_secret")
        payload = b'{"event":"payment.captured","id":"evt_test"}'

        expected = hmac.new(
            "test_secret".encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        is_valid = await adapter.verify_signature(payload, expected)

        assert is_valid is True

    @pytest.mark.anyio
    async def test_verify_signature_invalid(self):
        adapter = RazorpyStubAdapter(webhook_secret="test_secret")
        payload = b'{"event":"payment.captured","id":"evt_test"}'
        invalid_sig = "0" * 64

        is_valid = await adapter.verify_signature(payload, invalid_sig)

        assert is_valid is False

    @pytest.mark.anyio
    async def test_signature_deterministic(self):
        adapter = RazorpyStubAdapter(webhook_secret="test_secret")
        payload = b'{"event":"payment.captured","id":"evt_test"}'

        sig1 = await adapter.generate_signature(payload)
        sig2 = await adapter.generate_signature(payload)

        assert sig1 == sig2


class TestRazorpyStubAdapterSimulatePayment:
    """Test payment simulation."""

    @pytest.mark.anyio
    async def test_simulate_payment_success_for_00_amount(self):
        adapter = RazorpyStubAdapter()
        result = await adapter.simulate_payment(order_id="order_test", amount_paise=479900)

        assert result["success"] is True
        assert result["status"] == "captured"
        assert "payment_id" in result

    @pytest.mark.anyio
    async def test_simulate_payment_failure_for_99_amount(self):
        adapter = RazorpyStubAdapter()
        result = await adapter.simulate_payment(order_id="order_test", amount_paise=479999)

        assert result["success"] is False
        assert result["status"] == "failed"

    @pytest.mark.anyio
    async def test_simulate_payment_random_amount_succeeds(self):
        adapter = RazorpyStubAdapter()
        result = await adapter.simulate_payment(order_id="order_test", amount_paise=10001)

        assert result["success"] is True
        assert result["status"] == "captured"


class TestGetRazorpayStubAdapter:
    """Test adapter factory."""

    def test_returns_razorpay_stub_adapter_instance(self):
        adapter = get_razorpay_stub_adapter()
        assert isinstance(adapter, RazorpyStubAdapter)
