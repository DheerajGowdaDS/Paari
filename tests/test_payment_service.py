"""Tests for Payment Service."""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paari.payment.service import (
    AuthorizeResult,
    PaymentResult,
    PaymentService,
)


class TestPaymentServiceCreateSession:
    """Test payment session creation."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_maker(self, mock_session):
        """Create a mock session maker."""
        maker = MagicMock(return_value=mock_session)
        return maker

    @pytest.mark.asyncio
    async def test_create_payment_session_returns_session(self):
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_maker = MagicMock(return_value=mock_session)
        service = PaymentService(session_maker=mock_maker)

        mock_result = MagicMock()
        mock_result.first.return_value = MagicMock(
            id="tx-123",
            amount_paise=479900,
            currency="INR",
        )
        mock_session.execute.return_value = mock_result

        with patch("paari.payment.service.get_session_maker", return_value=mock_maker):
            session = await service.create_payment_session("tx-123")

        assert session.transaction_id == "tx-123"
        assert session.authorized_amount == 479900
        assert session.currency == "INR"
        assert session.status.value == "ACTIVE"

    @pytest.mark.asyncio
    async def test_create_payment_session_sets_expiry(self):
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_maker = MagicMock(return_value=mock_session)
        service = PaymentService(session_maker=mock_maker)

        mock_result = MagicMock()
        mock_result.first.return_value = MagicMock(
            id="tx-123",
            amount_paise=10000,
            currency="INR",
        )
        mock_session.execute.return_value = mock_result

        with patch("paari.payment.service.get_session_maker", return_value=mock_maker):
            session = await service.create_payment_session("tx-123")

        expected_min = datetime.now(UTC) + timedelta(minutes=9)
        expected_max = datetime.now(UTC) + timedelta(minutes=11)
        assert expected_min <= session.expires_at <= expected_max


class TestPaymentServiceCreateCapability:
    """Test payment capability creation."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_maker(self, mock_session):
        maker = MagicMock(return_value=mock_session)
        return maker

    @pytest.mark.asyncio
    async def test_create_capability_returns_capability(self):
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_maker = MagicMock(return_value=mock_session)
        service = PaymentService(session_maker=mock_maker)

        mock_result = MagicMock()
        mock_result.first.return_value = MagicMock(
            id="tx-123",
            amount_paise=479900,
        )
        mock_session.execute.return_value = mock_result

        with patch("paari.payment.service.get_session_maker", return_value=mock_maker):
            cap = await service.create_payment_capability("tx-123")

        assert cap.transaction_id == "tx-123"
        assert cap.action == "payment.execute"
        assert cap.max_amount == 479900
        assert cap.usage == "ONE_TIME"
        assert cap.used is False


class TestPaymentServiceGetAdapter:
    """Test adapter selection based on mode."""

    @pytest.mark.asyncio
    async def test_returns_stub_adapter_in_stub_mode(self):
        service = PaymentService()

        with patch("paari.config.settings") as mock_settings:
            mock_settings.razorpay_mode = "stub"
            adapter = await service.get_adapter()

        from paari.tools.adapters.razorpay_stub import RazorpyStubAdapter
        assert isinstance(adapter, RazorpyStubAdapter)

    @pytest.mark.asyncio
    async def test_returns_live_adapter_in_live_mode(self):
        mock_adapter = MagicMock()

        with patch("paari.config.settings") as mock_settings:
            mock_settings.razorpay_mode = "live"
            mock_settings.razorpay_key_id = "rzp_test_123"
            mock_settings.razorpay_key_secret = "secret_123"
            mock_settings.razorpay_webhook_secret = "webhook_secret"

            service = PaymentService()

            with patch("paari.adapters.razorpay_live.get_razorpay_adapter", return_value=mock_adapter):
                adapter = await service.get_adapter()

        assert adapter is mock_adapter


class TestPaymentServiceAuthorizePayment:
    """Test payment authorization through governance."""

    @pytest.fixture
    def mock_session(self):
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_maker(self, mock_session):
        maker = MagicMock(return_value=mock_session)
        return maker

    @pytest.mark.asyncio
    async def test_authorize_payment_deny_for_high_amount(self):
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_maker = MagicMock(return_value=mock_session)
        service = PaymentService(session_maker=mock_maker)

        mock_engine = MagicMock()
        mock_decision = MagicMock()
        mock_decision.decision = "DENY"
        mock_decision.failed_checks = [MagicMock(reason_code="AMOUNT_EXCEEDS_LIMIT")]
        mock_engine.evaluate = AsyncMock(return_value=mock_decision)

        service.governance_engine = mock_engine

        mock_ctx = MagicMock()
        mock_ctx.transaction = MagicMock(id="tx-123", amount_paise=2500000)

        with patch("paari.payment.service.GovernanceContext") as mock_gc:
            mock_gc.load = AsyncMock(return_value=mock_ctx)

            result = await service.authorize_payment("tx-123")

        assert result.authorized is False
        assert "DENY" in result.reason or "denied" in result.reason

    @pytest.mark.asyncio
    async def test_authorize_payment_allow_for_valid_amount(self):
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_maker = MagicMock(return_value=mock_session)
        service = PaymentService(session_maker=mock_maker)

        mock_engine = MagicMock()
        mock_decision = MagicMock()
        mock_decision.decision = "ALLOW"
        mock_engine.evaluate = AsyncMock(return_value=mock_decision)

        service.governance_engine = mock_engine

        mock_tx_row = MagicMock()
        mock_tx_row.id = "tx-123"
        mock_tx_row.amount_paise = 479900
        mock_tx_row.currency = "INR"

        mock_session.execute.return_value = MagicMock(first=MagicMock(
            id="tx-123",
            amount_paise=479900,
            currency="INR",
        ))

        mock_ps_row = MagicMock()
        mock_session.execute.return_value.first.side_effect = [
            mock_tx_row,
            mock_ps_row,
            MagicMock(),
        ]

        with patch("paari.payment.service.GovernanceContext") as mock_gc:
            mock_gc.load = AsyncMock(return_value=MagicMock(transaction=MagicMock(id="tx-123")))

            with patch.object(service, "create_payment_session", new_callable=AsyncMock) as mock_create_session:
                with patch.object(service, "create_payment_capability", new_callable=AsyncMock) as mock_create_cap:
                    mock_create_session.return_value = MagicMock(
                        id="ps-123",
                        display_id="PS-123",
                        authorized_amount=479900,
                        currency="INR",
                        expires_at=datetime.now(UTC) + timedelta(minutes=10),
                    )
                    mock_create_cap.return_value = MagicMock(
                        id="cap-123",
                        display_id="CAP-123",
                    )

                    result = await service.authorize_payment("tx-123")

        assert result.authorized is True
        assert result.session_id is not None
        assert result.capability_id is not None
