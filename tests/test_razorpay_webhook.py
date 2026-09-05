"""Tests for Razorpay Webhook Handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestHandlePaymentCaptured:
    """Test payment.captured event handling."""

    @pytest.mark.asyncio
    async def test_updates_transaction_to_payment_verified(self):
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_result = MagicMock()
        mock_result.first.return_value = MagicMock(
            id="tx-123",
            state="PAYMENT_PENDING",
        )
        mock_session.execute.return_value = mock_result

        mock_maker = MagicMock(return_value=mock_session)

        from paari.webhooks.razorpay_handler import handle_payment_captured

        event = {
            "event": "payment.captured",
            "id": "evt_test_123",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_123",
                        "order_id": "order_test_123",
                        "amount": 479900,
                    }
                }
            },
        }

        with patch("paari.webhooks.razorpay_handler.get_session_maker", return_value=mock_maker):
            result = await handle_payment_captured(event)

        assert result["status"] == "ok"
        assert result["transaction_id"] == "tx-123"
        assert result["payment_id"] == "pay_test_123"
        mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_skips_already_verified_transaction(self):
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_result = MagicMock()
        mock_result.first.return_value = MagicMock(
            id="tx-123",
            state="PAYMENT_VERIFIED",
        )
        mock_session.execute.return_value = mock_result

        mock_maker = MagicMock(return_value=mock_session)

        from paari.webhooks.razorpay_handler import handle_payment_captured

        event = {
            "event": "payment.captured",
            "id": "evt_test_123",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_123",
                        "order_id": "order_test_123",
                        "amount": 479900,
                    }
                }
            },
        }

        with patch("paari.webhooks.razorpay_handler.get_session_maker", return_value=mock_maker):
            result = await handle_payment_captured(event)

        assert result["status"] == "ok"
        assert result.get("already_verified") is True


class TestHandlePaymentFailed:
    """Test payment.failed event handling."""

    @pytest.mark.asyncio
    async def test_updates_transaction_to_payment_failed(self):
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_result = MagicMock()
        mock_result.first.return_value = MagicMock(
            id="tx-123",
            state="PAYMENT_PENDING",
        )
        mock_session.execute.return_value = mock_result

        mock_maker = MagicMock(return_value=mock_session)

        from paari.webhooks.razorpay_handler import handle_payment_failed

        event = {
            "event": "payment.failed",
            "id": "evt_test_456",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_456",
                        "order_id": "order_test_456",
                        "amount": 479900,
                    }
                }
            },
        }

        with patch("paari.webhooks.razorpay_handler.get_session_maker", return_value=mock_maker):
            result = await handle_payment_failed(event)

        assert result["status"] == "ok"
        assert result["transaction_id"] == "tx-123"


class TestHandleRazorpayEvent:
    """Test main event router."""

    @pytest.mark.asyncio
    async def test_routes_payment_captured(self):
        from paari.webhooks.razorpay_handler import handle_razorpay_event

        with patch("paari.webhooks.razorpay_handler.handle_payment_captured", new_callable=AsyncMock) as mock_handler:
            mock_handler.return_value = {"status": "ok", "transaction_id": "tx-123"}

            event = {
                "event": "payment.captured",
                "id": "evt_test_123",
            }

            result = await handle_razorpay_event(event)

            mock_handler.assert_called_once_with(event)
            assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_routes_payment_failed(self):
        from paari.webhooks.razorpay_handler import handle_razorpay_event

        with patch("paari.webhooks.razorpay_handler.handle_payment_failed", new_callable=AsyncMock) as mock_handler:
            mock_handler.return_value = {"status": "ok", "transaction_id": "tx-123"}

            event = {
                "event": "payment.failed",
                "id": "evt_test_456",
            }

            result = await handle_razorpay_event(event)

            mock_handler.assert_called_once_with(event)
            assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_returns_skipped_for_unknown_event(self):
        from paari.webhooks.razorpay_handler import handle_razorpay_event

        event = {
            "event": "unknown.event",
            "id": "evt_test_789",
        }

        result = await handle_razorpay_event(event)

        assert result["status"] == "skipped"
        assert "no_handler" in result["reason"]


class TestPersistAndProcessWebhook:
    """Test webhook persistence and processing."""

    @pytest.mark.asyncio
    async def test_inserts_webhook_event(self):
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_maker = MagicMock(return_value=mock_session)

        from paari.webhooks.razorpay_handler import persist_and_process_razorpay_webhook

        with patch("paari.webhooks.razorpay_handler.handle_razorpay_event", new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = {"status": "ok"}

            with patch("paari.webhooks.razorpay_handler.get_session_maker", return_value=mock_maker):
                result = await persist_and_process_razorpay_webhook(
                    event_type="payment.captured",
                    event_id="evt_unique_123",
                    payload={"test": "payload"},
                )

            assert result["status"] == "ok"
            mock_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_detects_duplicate_event(self):
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_session.execute.side_effect = Exception("UNIQUE constraint failed: Duplicate entry")

        mock_maker = MagicMock(return_value=mock_session)

        from paari.webhooks.razorpay_handler import persist_and_process_razorpay_webhook

        with patch("paari.webhooks.razorpay_handler.get_session_maker", return_value=mock_maker):
            result = await persist_and_process_razorpay_webhook(
                event_type="payment.captured",
                event_id="evt_duplicate_123",
                payload={"test": "payload"},
            )

        assert result["status"] == "ok"
        assert result["note"] == "duplicate_event"
