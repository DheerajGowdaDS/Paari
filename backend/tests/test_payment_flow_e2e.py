"""End-to-end tests for Razorpay payment flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPaymentFlowSuccessPath:
    """Test the success payment flow: governance ALLOW -> Razorpay -> verified."""

    @pytest.mark.asyncio
    async def test_success_flow_creates_order_and_verifies(self):
        from paari.payment.service import PaymentService

        mock_engine = MagicMock()
        mock_decision = MagicMock()
        mock_decision.decision = "ALLOW"
        mock_engine.evaluate = AsyncMock(return_value=mock_decision)

        mock_adapter = MagicMock()
        mock_adapter.create_order = AsyncMock(
            return_value={
                "source": "razorpay",
                "order_id": "order_test_success",
                "amount": 479900,
                "status": "created",
            }
        )
        mock_adapter.verify_signature = AsyncMock(return_value=True)

        from datetime import UTC, datetime, timedelta

        _sess_exp = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
        _transition_reads = {"n": 0}

        def _tx(state):
            return MagicMock(id="tx-success", amount_paise=479900, currency="INR", state=state)

        def _sess():
            return MagicMock(
                id="ps-success",
                transaction_id="tx-success",
                authorized_amount=479900,
                currency="INR",
                status="ACTIVE",
                expires_at=_sess_exp,
            )

        async def execute_side_effect(stmt, params=None):
            sql = str(stmt)
            res = MagicMock()
            if "FROM payment_sessions" in sql:
                res.first = MagicMock(return_value=_sess())
            elif "SELECT id, state FROM transactions" in sql:
                # state-machine transition reads: first GOVERNANCE_PENDING,
                # then AUTHORIZED, so the AUTHORIZED -> PAYMENT_PENDING
                # walk in authorize_payment is legal.
                _transition_reads["n"] += 1
                state = "GOVERNANCE_PENDING" if _transition_reads["n"] == 1 else "AUTHORIZED"
                res.first = MagicMock(return_value=_tx(state))
            elif "FROM transactions" in sql and "payment_sessions" not in sql:
                # authorize_payment reads see GOVERNANCE_PENDING; the bounded
                # money touch (create_razorpay_order) sees PAYMENT_PENDING.
                if "razorpay_order_id" in sql or "t.state" in sql:
                    res.first = MagicMock(return_value=_tx("PAYMENT_PENDING"))
                else:
                    res.first = MagicMock(return_value=_tx("GOVERNANCE_PENDING"))
            else:
                res.first = MagicMock(return_value=_tx("GOVERNANCE_PENDING"))
            return res

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_session.commit = AsyncMock()

        mock_maker = MagicMock(return_value=mock_session)

        service = PaymentService(
            governance_engine=mock_engine,
            razorpay_adapter=mock_adapter,
            session_maker=mock_maker,
        )

        with patch("paari.payment.service.GovernanceContext") as mock_gc:
            mock_gc.load = AsyncMock(
                return_value=MagicMock(
                    transaction=MagicMock(id="tx-success", amount_paise=479900),
                )
            )

            auth_result = await service.authorize_payment("tx-success")
            assert auth_result.authorized is True

        order_result = await service.create_razorpay_order("tx-success", "ps-success")
        assert order_result.success is True
        assert order_result.order_id == "order_test_success"
        _, order_kwargs = mock_adapter.create_order.await_args
        assert order_kwargs["amount_paise"] == 479900


class TestPaymentFlowBlockedPath:
    """Test the blocked payment flow: governance DENY -> no Razorpay call."""

    @pytest.mark.asyncio
    async def test_blocked_flow_does_not_create_order(self):
        from paari.payment.service import PaymentService

        mock_engine = MagicMock()
        mock_decision = MagicMock()
        mock_decision.decision = "DENY"
        mock_decision.failed_checks = [MagicMock(reason_code="AMOUNT_EXCEEDS_LIMIT")]
        mock_engine.evaluate = AsyncMock(return_value=mock_decision)

        mock_adapter = MagicMock()
        mock_adapter.create_order = AsyncMock()

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_maker = MagicMock(return_value=mock_session)

        service = PaymentService(
            governance_engine=mock_engine,
            razorpay_adapter=mock_adapter,
            session_maker=mock_maker,
        )

        with patch("paari.payment.service.GovernanceContext") as mock_gc:
            mock_gc.load = AsyncMock(
                return_value=MagicMock(
                    transaction=MagicMock(id="tx-blocked", amount_paise=2500000),
                )
            )

            auth_result = await service.authorize_payment("tx-blocked")
            assert auth_result.authorized is False
            assert "DENY" in auth_result.reason or "denied" in auth_result.reason

        mock_adapter.create_order.assert_not_called()


class TestPaymentFlowReviewEscalation:
    """Test review escalation: governance REVIEW -> no payment until approved."""

    @pytest.mark.asyncio
    async def test_review_flow_returns_review_required(self):
        from paari.payment.service import PaymentService

        mock_engine = MagicMock()
        mock_decision = MagicMock()
        mock_decision.decision = "REVIEW"
        mock_engine.evaluate = AsyncMock(return_value=mock_decision)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_maker = MagicMock(return_value=mock_session)

        service = PaymentService(
            governance_engine=mock_engine,
            session_maker=mock_maker,
        )

        with patch("paari.payment.service.GovernanceContext") as mock_gc:
            mock_gc.load = AsyncMock(
                return_value=MagicMock(
                    transaction=MagicMock(id="tx-review", amount_paise=1500000),
                )
            )

            auth_result = await service.authorize_payment("tx-review")

        assert auth_result.authorized is False
        assert "review" in auth_result.reason.lower()


class TestWebhookIdempotency:
    """Test that duplicate webhook events are handled correctly."""

    @pytest.mark.asyncio
    async def test_duplicate_webhook_returns_ok_without_reprocessing(self):
        from paari.webhooks.razorpay_handler import persist_and_process_razorpay_webhook

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute.side_effect = Exception("UNIQUE constraint failed")

        mock_maker = MagicMock(return_value=mock_session)

        with patch("paari.webhooks.razorpay_handler.get_session_maker", return_value=mock_maker):
            result = await persist_and_process_razorpay_webhook(
                event_type="payment.captured",
                event_id="evt_duplicate_123",
                payload={"test": "payload"},
            )

        assert result["status"] == "ok"
        assert result["note"] == "duplicate_event"


class TestSignatureVerification:
    """Test payment signature verification."""

    @pytest.mark.asyncio
    async def test_valid_signature_passes_verification(self):
        from paari.payment.service import PaymentService

        mock_adapter = MagicMock()
        mock_adapter.verify_checkout_signature = AsyncMock(return_value=True)

        service = PaymentService(razorpay_adapter=mock_adapter)

        is_valid = await service.verify_payment_signature(
            payment_id="pay_test_123",
            order_id="order_test_123",
            signature="valid_signature",
            payload=b'{"test":"payload"}',
        )

        assert is_valid is True
        mock_adapter.verify_checkout_signature.assert_called_once_with(
            "order_test_123", "pay_test_123", "valid_signature"
        )

    @pytest.mark.asyncio
    async def test_invalid_signature_fails_verification(self):
        from paari.payment.service import PaymentService

        mock_adapter = MagicMock()
        mock_adapter.verify_checkout_signature = AsyncMock(return_value=False)

        service = PaymentService(razorpay_adapter=mock_adapter)

        is_valid = await service.verify_payment_signature(
            payment_id="pay_test_123",
            order_id="order_test_123",
            signature="invalid_signature",
            payload=b'{"test":"payload"}',
        )

        assert is_valid is False
