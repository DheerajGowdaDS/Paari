"""Checkout signature scheme: HMAC-SHA256(order_id|payment_id, key_secret)."""

from __future__ import annotations

import pytest

KNOWN_SIG = "e05fa2e9e9ebb182174b7ef844f2feaa33a3bc27c1a4c7f445dafbeb64b76252"


class TestLiveCheckoutSignature:
    async def test_known_vector(self):
        from paari.adapters.razorpay_live import RazorpayLiveAdapter

        adapter = RazorpayLiveAdapter("kid", "secret123", "whsec")
        assert (
            await adapter.verify_checkout_signature("order_test_1", "pay_test_1", KNOWN_SIG) is True
        )

    async def test_tampered_signature_rejected(self):
        from paari.adapters.razorpay_live import RazorpayLiveAdapter

        adapter = RazorpayLiveAdapter("kid", "secret123", "whsec")
        assert (
            await adapter.verify_checkout_signature(
                "order_test_1", "pay_test_1", KNOWN_SIG[:-1] + "0"
            )
            is False
        )

    async def test_wrong_secret_rejected(self):
        from paari.adapters.razorpay_live import RazorpayLiveAdapter

        adapter = RazorpayLiveAdapter("kid", "other_secret", "whsec")
        assert (
            await adapter.verify_checkout_signature("order_test_1", "pay_test_1", KNOWN_SIG)
            is False
        )

    async def test_empty_inputs_rejected(self):
        from paari.adapters.razorpay_live import RazorpayLiveAdapter

        adapter = RazorpayLiveAdapter("kid", "secret123", "whsec")
        assert await adapter.verify_checkout_signature("", "", "") is False

    async def test_webhook_secret_does_not_verify_checkout(self):
        import hashlib
        import hmac

        from paari.adapters.razorpay_live import RazorpayLiveAdapter

        adapter = RazorpayLiveAdapter("kid", "secret123", "webhook_only")
        webhook_sig = hmac.new(
            b"webhook_only", b"order_test_1|pay_test_1", hashlib.sha256
        ).hexdigest()
        assert (
            await adapter.verify_checkout_signature("order_test_1", "pay_test_1", webhook_sig)
            is False
        )


class TestStubCheckoutSignature:
    async def test_roundtrip(self):
        import hashlib
        import hmac

        from paari.tools.adapters.razorpay_stub import RazorpyStubAdapter

        adapter = RazorpyStubAdapter(webhook_secret="s3cr3t")
        sig = hmac.new(b"s3cr3t", b"order_abc|pay_abc", hashlib.sha256).hexdigest()
        assert await adapter.verify_checkout_signature("order_abc", "pay_abc", sig) is True
        assert await adapter.verify_checkout_signature("order_abc", "pay_abc", "bad") is False


class TestServiceDelegation:
    async def test_service_uses_checkout_scheme(self):
        from unittest.mock import AsyncMock, MagicMock

        from paari.payment.service import PaymentService

        mock_adapter = MagicMock()
        mock_adapter.verify_checkout_signature = AsyncMock(return_value=True)
        service = PaymentService(razorpay_adapter=mock_adapter)
        assert await service.verify_payment_signature("pay_1", "order_1", "sig") is True
        mock_adapter.verify_checkout_signature.assert_called_once_with("order_1", "pay_1", "sig")


class TestSettleHelper:
    async def test_not_ready_without_verified_state(self, monkeypatch):
        from paari.payment import settle as settle_mod

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def execute(self, *a, **k):
                from types import SimpleNamespace

                return SimpleNamespace(
                    first=lambda: SimpleNamespace(id="tx1", state="PAYMENT_PENDING")
                )

        monkeypatch.setattr("paari.db.engine.get_session_maker", lambda: lambda: _Session())
        result = await settle_mod.settle_verified_transaction("tx1")
        assert result == {"fulfilled": False, "reason": "not_ready:PAYMENT_PENDING"}

    async def test_missing_transaction(self, monkeypatch):
        from paari.payment import settle as settle_mod

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def execute(self, *a, **k):
                from types import SimpleNamespace

                return SimpleNamespace(first=lambda: None)

        monkeypatch.setattr("paari.db.engine.get_session_maker", lambda: lambda: _Session())
        result = await settle_mod.settle_verified_transaction("nope")
        assert result == {"fulfilled": False, "reason": "transaction_not_found"}


class TestWebhookAutoSettle:
    async def test_captured_triggers_settle(self, monkeypatch):
        from unittest.mock import AsyncMock

        import paari.webhooks.razorpay_handler as handler_mod

        async def _fake_captured(event):
            return {"status": "ok", "transaction_id": "tx1"}

        settle_mock = AsyncMock(return_value={"fulfilled": True, "order_id": "o1"})
        monkeypatch.setattr(handler_mod, "handle_payment_captured", _fake_captured)
        monkeypatch.setattr("paari.payment.settle.settle_verified_transaction", settle_mock)
        result = await handler_mod.handle_razorpay_event(
            {"event": "payment.captured", "id": "e1", "payload": {}}
        )
        assert result["settled"] is True
        settle_mock.assert_awaited_once_with("tx1")

    async def test_synthetic_events_skip_settle(self, monkeypatch):
        from unittest.mock import AsyncMock

        import paari.webhooks.razorpay_handler as handler_mod

        async def _fake_captured(event):
            return {"status": "ok", "transaction_id": "tx1"}

        settle_mock = AsyncMock(return_value={"fulfilled": True})
        monkeypatch.setattr(handler_mod, "handle_payment_captured", _fake_captured)
        monkeypatch.setattr("paari.payment.settle.settle_verified_transaction", settle_mock)
        result = await handler_mod.handle_razorpay_event(
            {"event": "payment.captured", "id": "e1", "payload": {}, "synthetic": True}
        )
        assert "settled" not in result
        settle_mock.assert_not_awaited()

    async def test_failed_payment_never_settles(self, monkeypatch):
        from unittest.mock import AsyncMock

        import paari.webhooks.razorpay_handler as handler_mod

        settle_mock = AsyncMock()
        monkeypatch.setattr("paari.payment.settle.settle_verified_transaction", settle_mock)
        await handler_mod.handle_razorpay_event(
            {"event": "payment.unknown", "id": "e1", "payload": {}}
        )
        settle_mock.assert_not_awaited()


pytestmark = pytest.mark.asyncio
