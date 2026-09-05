"""Phase-1 proof tests: governed authorize + bounded money touch.

Mirrors tests/test_payment_flow_e2e.py style (mock engine/adapter).
Covers: ALLOW bounded, DENY no-mint, REVIEW no-money, 4 session
boundaries, gateway authorize gated by GovernanceEngine.evaluate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _tx_row(tx_id="tx-1", amount=120_000, state="PAYMENT_PENDING"):
    return MagicMock(id=tx_id, amount_paise=amount, currency="INR", state=state)


def _sess_row(
    sid="ps-1",
    tx_id="tx-1",
    amount=120_000,
    status="ACTIVE",
    expired=False,
):
    exp = datetime.now(UTC) + timedelta(minutes=-1 if expired else 10)
    return MagicMock(
        id=sid,
        transaction_id=tx_id,
        authorized_amount=amount,
        currency="INR",
        status=status,
        expires_at=exp.isoformat(),
    )


def _maker_for(firsts: list):
    """Mock session_maker whose session.execute(...).first() pops from firsts."""
    queue = list(firsts)

    def _first(*a, **k):
        return queue.pop(0) if queue else None

    mock_result = MagicMock()
    mock_result.first = MagicMock(side_effect=_first)
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    return MagicMock(return_value=mock_session), mock_session


def _allow_engine():
    eng = MagicMock()
    d = MagicMock()
    d.decision = "ALLOW"
    eng.evaluate = AsyncMock(return_value=d)
    return eng


def _deny_engine():
    eng = MagicMock()
    d = MagicMock()
    d.decision = "DENY"
    d.failed_checks = [MagicMock(reason_code="LIMIT_EXCEEDED")]
    eng.evaluate = AsyncMock(return_value=d)
    return eng


def _review_engine():
    eng = MagicMock()
    d = MagicMock()
    d.decision = "REVIEW"
    eng.evaluate = AsyncMock(return_value=d)
    return eng


class TestPhase1AllowBounded:
    @pytest.mark.asyncio
    async def test_allow_authorizes_and_order_is_bounded(self):
        from paari.payment.service import PaymentService

        eng = _allow_engine()
        adapter = MagicMock()
        adapter.create_order = AsyncMock(
            return_value={"order_id": "order_bounded_1", "status": "created"}
        )
        maker, _ = _maker_for(
            [
                _tx_row("tx-allow", 120_000, "PAYMENT_PENDING"),
                _sess_row("ps-allow", "tx-allow", 120_000),
            ]
        )

        svc = PaymentService(governance_engine=eng, razorpay_adapter=adapter, session_maker=maker)
        res = await svc.create_razorpay_order("tx-allow", "ps-allow")
        assert res.success is True
        assert res.order_id == "order_bounded_1"
        _, kwargs = adapter.create_order.await_args
        assert kwargs["amount_paise"] == 120_000


class TestPhase1Deny:
    @pytest.mark.asyncio
    async def test_deny_mints_nothing_and_no_order(self):
        from paari.payment.service import PaymentService

        eng = _deny_engine()
        adapter = MagicMock()
        adapter.create_order = AsyncMock()
        maker, _ = _maker_for([])
        svc = PaymentService(governance_engine=eng, razorpay_adapter=adapter, session_maker=maker)
        svc.create_payment_session = AsyncMock()  # type: ignore[method-assign]
        svc.create_payment_capability = AsyncMock()  # type: ignore[method-assign]

        with patch("paari.payment.service.GovernanceContext") as mock_gc:
            mock_gc.load = AsyncMock(
                return_value=MagicMock(transaction=MagicMock(id="tx-deny", amount_paise=900_000))
            )
            auth = await svc.authorize_payment("tx-deny")
        assert auth.authorized is False
        svc.create_payment_session.assert_not_called()
        svc.create_payment_capability.assert_not_called()
        adapter.create_order.assert_not_called()


class TestPhase1Review:
    @pytest.mark.asyncio
    async def test_review_returns_review_required_no_money(self):
        from paari.payment.service import PaymentService

        eng = _review_engine()
        adapter = MagicMock()
        adapter.create_order = AsyncMock()
        maker, _ = _maker_for([])
        svc = PaymentService(governance_engine=eng, razorpay_adapter=adapter, session_maker=maker)
        svc.create_payment_session = AsyncMock()  # type: ignore[method-assign]
        svc.create_payment_capability = AsyncMock()  # type: ignore[method-assign]

        with patch("paari.payment.service.GovernanceContext") as mock_gc:
            mock_gc.load = AsyncMock(
                return_value=MagicMock(transaction=MagicMock(id="tx-review", amount_paise=120_000))
            )
            auth = await svc.authorize_payment("tx-review")
        assert auth.authorized is False
        assert auth.reason is not None and "review" in auth.reason.lower()
        svc.create_payment_session.assert_not_called()
        adapter.create_order.assert_not_called()


class TestPhase1Boundaries:
    @pytest.mark.asyncio
    async def test_forged_session_refused(self):
        from paari.payment.service import PaymentService

        adapter = MagicMock()
        adapter.create_order = AsyncMock()
        maker, _ = _maker_for([_tx_row("tx-b", 120_000, "PAYMENT_PENDING"), None])
        svc = PaymentService(razorpay_adapter=adapter, session_maker=maker)
        res = await svc.create_razorpay_order("tx-b", "PS-FORGED")
        assert res.success is False
        assert res.reason == "session_not_found"
        adapter.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_foreign_session_refused(self):
        from paari.payment.service import PaymentService

        adapter = MagicMock()
        adapter.create_order = AsyncMock()
        maker, _ = _maker_for(
            [_tx_row("tx-b", 120_000, "PAYMENT_PENDING"), _sess_row("ps-x", "tx-other", 120_000)]
        )
        svc = PaymentService(razorpay_adapter=adapter, session_maker=maker)
        res = await svc.create_razorpay_order("tx-b", "ps-x")
        assert res.success is False
        assert res.reason == "session_tx_mismatch"
        adapter.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_inactive_session_refused(self):
        from paari.payment.service import PaymentService

        adapter = MagicMock()
        adapter.create_order = AsyncMock()
        maker, _ = _maker_for(
            [
                _tx_row("tx-b", 120_000, "PAYMENT_PENDING"),
                _sess_row("ps-b", "tx-b", 120_000, status="COMPLETED"),
            ]
        )
        svc = PaymentService(razorpay_adapter=adapter, session_maker=maker)
        res = await svc.create_razorpay_order("tx-b", "ps-b")
        assert res.success is False
        assert res.reason == "session_not_active"
        adapter.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_amount_mismatch_refused(self):
        from paari.payment.service import PaymentService

        adapter = MagicMock()
        adapter.create_order = AsyncMock()
        maker, _ = _maker_for(
            [_tx_row("tx-b", 120_000, "PAYMENT_PENDING"), _sess_row("ps-b", "tx-b", 999_999)]
        )
        svc = PaymentService(razorpay_adapter=adapter, session_maker=maker)
        res = await svc.create_razorpay_order("tx-b", "ps-b")
        assert res.success is False
        assert res.reason == "amount_mismatch"
        adapter.create_order.assert_not_called()


class TestGatewayAuthorizeGated:
    @pytest.mark.asyncio
    async def test_deny_cannot_mint_session_via_gateway(self):
        from fastapi import HTTPException

        from paari.api import gateway as gw

        maker, _ = _maker_for([MagicMock(id="tx-deny")])
        deny_eng = _deny_engine()
        with (
            patch.object(gw, "get_session_maker", return_value=maker),
            patch.object(gw, "GovernanceContext") as mock_gc,
            patch.object(gw, "get_governance_engine", return_value=deny_eng),
        ):
            mock_gc.load = AsyncMock(return_value=MagicMock(transaction=MagicMock(id="tx-deny")))
            with pytest.raises(HTTPException) as exc:
                await gw.authorize_payment("TXN-DENY")
            assert exc.value.status_code == 409
        deny_eng.evaluate.assert_awaited_once()
