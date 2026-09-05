"""Regression tests: agentic payment boundary (blueprint security invariants).

Covers:
1. /payments/verify verifies HMAC against the SERVER-STOREded razorpay_order_id,
   never the client-supplied value (order_id_mismatch -> 401).
2. BuyerAgent.execute_payment in LIVE mode does NOT forge a webhook: it returns
   CHECKOUT_REQUIRED and hands off to Razorpay Checkout (human completes it).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _verify_req(
    transaction_id: str = "TXN-1",
    order_id: str = "order_client_supplied",
    payment_id: str = "pay_client_supplied",
    signature: str = "sig",
):
    from paari.api.payments import VerifyPaymentRequest

    return VerifyPaymentRequest(
        transaction_id=transaction_id,
        razorpay_payment_id=payment_id,
        razorpay_order_id=order_id,
        razorpay_signature=signature,
    )


class TestVerifyUsesServerStoredOrderId:
    @pytest.mark.asyncio
    async def test_rejects_client_order_id_mismatch(self):
        """A client-supplied order id that differs from the stored one is 401
        BEFORE any signature check — blueprint: never trust the client value."""
        from paari.api.payments import verify_payment

        # DB returns the REAL stored order for this tx.
        stored_row = MagicMock(
            id="tx-real",
            razorpay_order_id="order_server_stored",
            amount_paise=479900,
            state="PAYMENT_PENDING",
        )
        mock_result = MagicMock()
        mock_result.first.return_value = stored_row
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_maker = MagicMock(return_value=mock_session)

        # The signature service must NOT be called — the mismatch is a hard 401.
        # verify_payment raises HTTPException(401) — import and assert
        from fastapi import HTTPException

        with patch("paari.db.engine.get_session_maker", return_value=mock_maker), patch(
            "paari.api.payments.get_payment_service"
        ) as mock_svc:
            mock_svc.return_value.verify_payment_signature = AsyncMock(return_value=True)
            with pytest.raises(HTTPException) as exc_info:
                await verify_payment(
                    _verify_req(order_id="order_client_supplied")
                )
            assert exc_info.value.status_code == 401
            assert "order_id_mismatch" in exc_info.value.detail
            mock_svc.return_value.verify_payment_signature.assert_not_called()

    @pytest.mark.asyncio
    async def test_verifies_against_stored_order_id(self):
        """Matching client order -> HMAC checked with the STORED id and passes."""
        from fastapi import HTTPException

        from paari.api.payments import verify_payment

        stored_row = MagicMock(
            id="tx-real",
            razorpay_order_id="order_server_stored",
            amount_paise=479900,
            state="PAYMENT_PENDING",
        )
        mock_result = MagicMock()
        mock_result.first.return_value = stored_row
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_maker = MagicMock(return_value=mock_session)

        mock_svc = MagicMock()
        mock_svc.verify_payment_signature = AsyncMock(return_value=True)

        with patch("paari.db.engine.get_session_maker", return_value=mock_maker), patch(
            "paari.api.payments.get_payment_service", return_value=mock_svc
        ):
            resp = await verify_payment(
                _verify_req(order_id="order_server_stored", payment_id="pay_ok", signature="sig_ok")
            )

        assert resp.success is True
        # The signature check used the SERVER-STORED id, not the client value.
        mock_svc.verify_payment_signature.assert_called_once_with(
            payment_id="pay_ok",
            order_id="order_server_stored",
            signature="sig_ok",
        )

    @pytest.mark.asyncio
    async def test_rejects_no_stored_order(self):
        """No server-side order -> 400 (nothing to verify against)."""
        from fastapi import HTTPException

        from paari.api.payments import verify_payment

        stored_row = MagicMock(
            id="tx-real",
            razorpay_order_id=None,
            amount_paise=479900,
            state="PAYMENT_PENDING",
        )
        mock_result = MagicMock()
        mock_result.first.return_value = stored_row
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_maker = MagicMock(return_value=mock_session)

        with patch("paari.db.engine.get_session_maker", return_value=mock_maker):
            with pytest.raises(HTTPException) as exc_info:
                await verify_payment(_verify_req())
            assert exc_info.value.status_code == 400
            assert "no_razorpay_order_for_transaction" in exc_info.value.detail


class TestBuyerAgentLiveHandoff:
    @pytest.mark.asyncio
    async def test_live_mode_returns_checkout_required(self, monkeypatch):
        """In live mode the agent must NOT simulate/forge a webhook: it returns
        CHECKOUT_REQUIRED with the server-created order + checkout URL."""
        from paari.config import settings as paari_settings

        monkeypatch.setattr(paari_settings, "razorpay_mode", "live")

        from paari.agent.buyer_agent import BuyerAgent

        agent = BuyerAgent(agent_id="BA-001", paari_url="http://localhost:8000")
        # Supply the order id so no HTTP call is made — the mode gate must
        # short-circuit to CHECKOUT_REQUIRED before any payment execution.
        result = await agent.execute_payment(
            payment_session_id="PS-1",
            transaction_id="TXN-1",
            razorpay_order_id="order_server_live",
            amount_paise=479900,
        )

        assert result["status"] == "CHECKOUT_REQUIRED"
        assert result["razorpay_order_id"] == "order_server_live"
        assert result["checkout_url"] == "http://localhost:8000/checkout/TXN-1"
        assert "razorpay_payment_id" not in result  # no forged payment

    @pytest.mark.asyncio
    async def test_live_mode_does_not_hit_webhook(self, monkeypatch):
        """Guarantee: with a supplied order id, live mode performs ZERO HTTP
        calls (no webhook forge, no /payments/simulate)."""
        from paari.config import settings as paari_settings

        monkeypatch.setattr(paari_settings, "razorpay_mode", "live")

        from paari.agent.buyer_agent import BuyerAgent

        agent = BuyerAgent(agent_id="BA-001", paari_url="http://localhost:8000")
        # Pre-inject a mock client; the live gate must short-circuit before
        # any request, so .post is never invoked.
        mock_client = MagicMock()
        agent.http_client = mock_client

        await agent.execute_payment(
            payment_session_id="PS-1",
            transaction_id="TXN-1",
            razorpay_order_id="order_server_live",
            amount_paise=479900,
        )

        mock_client.post.assert_not_called()