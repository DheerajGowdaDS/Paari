"""Payment API router.

Endpoints:
- POST /payments/create — Authorize and create payment session
- POST /payments/verify — Verify payment signature and confirm
- POST /payments/mandate-charge — Charge a pre-authorized mandate (bounded)
- GET /payments/{transaction_id} — Get payment status
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from paari.payment.service import get_payment_service

_log = logging.getLogger("paari.payments")
router = APIRouter(prefix="/payments", tags=["payments"])


class CreatePaymentRequest(BaseModel):
    """Request to create/authorize a payment for a transaction."""

    transaction_id: str = Field(..., description="Transaction UUID or display_id")


class CreatePaymentResponse(BaseModel):
    """Response from payment authorization."""

    model_config = ConfigDict(extra="forbid")

    authorized: bool
    session_id: str | None = None
    session_display_id: str | None = None
    capability_id: str | None = None
    capability_display_id: str | None = None
    authorized_amount: int | None = None
    currency: str | None = None
    expires_at: str | None = None
    reason: str | None = None


class VerifyPaymentRequest(BaseModel):
    """Request to verify a payment after Razorpay checkout."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(..., description="Transaction UUID or display_id")
    razorpay_payment_id: str = Field(..., description="Razorpay payment ID")
    razorpay_order_id: str = Field(..., description="Razorpay order ID")
    razorpay_signature: str = Field(..., description="X-Razorpay-Signature header")


class VerifyPaymentResponse(BaseModel):
    """Response from payment verification."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    order_id: str | None = None
    payment_id: str | None = None
    status: str | None = None
    reason: str | None = None


class PaymentStatusResponse(BaseModel):
    """Response with payment status."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    session_id: str | None = None
    session_display_id: str | None = None
    order_id: str | None = None
    payment_id: str | None = None
    status: str
    authorized_amount: int | None = None
    currency: str | None = None


@router.post("/create", response_model=CreatePaymentResponse)
async def create_payment(req: CreatePaymentRequest) -> CreatePaymentResponse:
    """Authorize and create a payment session for a transaction.

    Flow:
    1. Load governance context
    2. Evaluate governance rules
    3. If ALLOW: create payment session + capability
    4. If DENY/REVIEW: return unauthorized
    """
    service = get_payment_service()

    try:
        result = await service.authorize_payment(req.transaction_id)
        return CreatePaymentResponse(
            authorized=result.authorized,
            session_id=result.session_id,
            session_display_id=result.session_display_id,
            capability_id=result.capability_id,
            capability_display_id=result.capability_display_id,
            authorized_amount=result.authorized_amount,
            currency=result.currency,
            expires_at=result.expires_at,
            reason=result.reason,
        )
    except Exception as exc:
        _log.error("Payment creation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"payment_creation_failed: {exc}",
        )


@router.post("/verify", response_model=VerifyPaymentResponse)
async def verify_payment(req: VerifyPaymentRequest) -> VerifyPaymentResponse:
    """Verify payment signature and confirm payment.

    In stub mode, simulates webhook to confirm payment.
    In live mode, verifies the signature and processes the payment.
    """
    service = get_payment_service()

    try:
        from sqlalchemy import text
        from paari.db.engine import get_session_maker

        # Load the transaction FIRST so the HMAC is verified against the
        # server-side stored order ID, never the client-supplied value
        # (blueprint: "use the server-side stored order ID, not simply trust
        # the razorpay_order_id returned by the client").
        maker = get_session_maker()
        async with maker() as session:
            tx_row = (
                await session.execute(
                    text(
                        "SELECT t.id, t.razorpay_order_id, t.amount_paise, t.state "
                        "FROM transactions t WHERE t.id = :x OR t.display_id = :x"
                    ),
                    {"x": req.transaction_id},
                )
            ).first()

            if tx_row is None:
                return VerifyPaymentResponse(
                    success=False,
                    reason="transaction_not_found",
                )

            tx_id = tx_row.id
            tx_state = tx_row.state
            stored_order_id = tx_row.razorpay_order_id

            if not stored_order_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="no_razorpay_order_for_transaction",
                )

            # Anti-tamper: the client-reported order must match the stored one.
            if req.razorpay_order_id != stored_order_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="order_id_mismatch",
                )

            is_valid = await service.verify_payment_signature(
                payment_id=req.razorpay_payment_id,
                order_id=stored_order_id,
                signature=req.razorpay_signature,
            )

            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid_signature",
                )

            if tx_state in (
                "PAYMENT_VERIFIED",
                "FULFILLMENT_PENDING",
                "ORDER_CONFIRMED",
                "COMPLETED",
            ):
                return VerifyPaymentResponse(
                    success=True,
                    order_id=stored_order_id,
                    payment_id=req.razorpay_payment_id,
                    status="already_verified",
                )

            await session.execute(
                text(
                    "UPDATE transactions SET razorpay_payment_id = :pid, state = 'PAYMENT_VERIFIED' "
                    "WHERE id = :tid"
                ),
                {"pid": req.razorpay_payment_id, "tid": tx_id},
            )

            await session.execute(
                text(
                    "UPDATE payment_sessions SET status = 'COMPLETED' "
                    "WHERE transaction_id = :tid AND status = 'ACTIVE'"
                ),
                {"tid": tx_id},
            )

            await session.commit()

            try:
                from paari.payment.settle import settle_verified_transaction

                settle = await settle_verified_transaction(tx_id)
                if not settle.get("fulfilled"):
                    _log.info(
                        "Post-verify settle pending for %s: %s",
                        req.transaction_id,
                        settle.get("reason"),
                    )
            except Exception as exc:
                _log.warning("Post-verify settle failed: %s", exc)

            return VerifyPaymentResponse(
                success=True,
                order_id=stored_order_id,
                payment_id=req.razorpay_payment_id,
                status="verified",
            )

    except HTTPException:
        raise
    except Exception as exc:
        _log.error("Payment verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"payment_verification_failed: {exc}",
        )


@router.get("/{transaction_id}", response_model=PaymentStatusResponse)
async def get_payment_status(transaction_id: str) -> PaymentStatusResponse:
    """Get the current payment status for a transaction."""
    from sqlalchemy import text
    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT t.id, t.display_id, t.razorpay_order_id, t.razorpay_payment_id, "
                    "t.amount_paise, t.currency, t.state, "
                    "ps.id AS session_id, ps.display_id AS session_display_id, ps.status AS session_status "
                    "FROM transactions t "
                    "LEFT JOIN payment_sessions ps ON ps.transaction_id = t.id AND ps.status = 'ACTIVE' "
                    "WHERE t.id = :x OR t.display_id = :x"
                ),
                {"x": transaction_id},
            )
        ).first()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"transaction not found: {transaction_id}",
            )

        return PaymentStatusResponse(
            transaction_id=row.display_id or row.id,
            session_id=row.session_id,
            session_display_id=row.session_display_id,
            order_id=row.razorpay_order_id,
            payment_id=row.razorpay_payment_id,
            status=row.state,
            authorized_amount=int(row.amount_paise) if row.amount_paise else None,
            currency=row.currency or "INR",
        )


class SimulatePaymentRequest(BaseModel):
    """Request to simulate a payment in stub mode."""

    model_config = ConfigDict(extra="forbid")

    payment_session_id: str = Field(..., description="Payment session ID")
    razorpay_order_id: str | None = Field(default=None, description="Razorpay order ID")
    amount_paise: int | None = Field(default=None, description="Amount in paise")
    simulate_failure: bool = Field(
        default=False, description="If true, simulate PAYMENT_FAILED instead of VERIFIED"
    )


class SimulatePaymentResponse(BaseModel):
    """Response from payment simulation."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    payment_session_id: str
    razorpay_payment_id: str | None = None
    razorpay_order_id: str | None = None
    status: str
    simulated: bool = True


class TransactionResponse(BaseModel):
    """Response with full transaction details."""

    model_config = ConfigDict(extra="forbid")

    id: str
    display_id: str | None = None
    merchant_id: str
    buyer_agent_id: str
    merchant_agent_id: str | None = None
    quote_id: str | None = None
    amount_paise: int
    currency: str
    state: str
    policy_version: str
    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None
    payment_session_id: str | None = None
    created_at: str | None = None


@router.get("/transaction/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(transaction_id: str) -> TransactionResponse:
    """Get full transaction details.

    GET /payments/transaction/{transaction_id}
    """
    from sqlalchemy import text
    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT id, display_id, merchant_id, buyer_agent_id, merchant_agent_id, "
                    "quote_id, amount_paise, currency, state, policy_version, "
                    "razorpay_order_id, razorpay_payment_id, payment_session_id, created_at "
                    "FROM transactions "
                    "WHERE id = :x OR display_id = :x"
                ),
                {"x": transaction_id},
            )
        ).first()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction not found: {transaction_id}",
            )

        return TransactionResponse(
            id=row.id,
            display_id=row.display_id,
            merchant_id=row.merchant_id,
            buyer_agent_id=row.buyer_agent_id,
            merchant_agent_id=row.merchant_agent_id,
            quote_id=row.quote_id,
            amount_paise=int(row.amount_paise),
            currency=row.currency or "INR",
            state=row.state,
            policy_version=row.policy_version,
            razorpay_order_id=row.razorpay_order_id,
            razorpay_payment_id=row.razorpay_payment_id,
            payment_session_id=row.payment_session_id,
            created_at=row.created_at.isoformat() if row.created_at else None,
        )


@router.post("/simulate", response_model=SimulatePaymentResponse)
async def simulate_payment(req: SimulatePaymentRequest) -> SimulatePaymentResponse:
    """Simulate a payment in stub mode.

    POST /payments/simulate

    This endpoint is used by the Buyer Agent to simulate payment
    completion in stub mode without actually calling Razorpay.
    """
    import uuid
    from datetime import UTC

    from sqlalchemy import text
    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        # Find session and transaction
        row = (
            await session.execute(
                text(
                    "SELECT ps.id, ps.transaction_id, ps.authorized_amount, ps.status, "
                    "t.display_id AS tx_display_id "
                    "FROM payment_sessions ps "
                    "JOIN transactions t ON t.id = ps.transaction_id "
                    "WHERE ps.id = :sid OR ps.display_id = :sid"
                ),
                {"sid": req.payment_session_id},
            )
        ).first()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment session not found",
            )

        if row.status not in ("ACTIVE",):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment session not active: {row.status}",
            )

        tx_id = row.transaction_id

        razorpay_order_id = req.razorpay_order_id or f"order_{uuid.uuid4().hex[:12]}"
        razorpay_payment_id = f"pay_{uuid.uuid4().hex[:12]}"

        if req.simulate_failure:
            from paari.governance_engine.state_machine import transition, walk_to

            try:
                await walk_to(session, tx_id, "PAYMENT_FAILED")
            except Exception:
                await session.execute(
                    text("UPDATE transactions SET state='PAYMENT_FAILED' WHERE id=:tid"),
                    {"tid": tx_id},
                )
            await session.execute(
                text(
                    "INSERT INTO payment_events (id, transaction_id, event_type, payload_json) VALUES (:id, :tid, 'payment.failed', :payload)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "tid": tx_id,
                    "payload": '{"reason":"simulated_failure"}',
                },
            )
            await session.execute(
                text("UPDATE payment_sessions SET status='FAILED' WHERE id=:sid"),
                {"sid": row.id},
            )
            await session.commit()
            _log.info("Simulated PAYMENT_FAILED for session %s", req.payment_session_id)
            return SimulatePaymentResponse(
                success=False,
                payment_session_id=req.payment_session_id,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_order_id=razorpay_order_id,
                status="FAILED",
                simulated=True,
            )

        await session.execute(
            text(
                "UPDATE transactions SET razorpay_order_id=:order_id, razorpay_payment_id=:payment_id, state='PAYMENT_VERIFIED' WHERE id=:tid"
            ),
            {
                "order_id": razorpay_order_id,
                "payment_id": razorpay_payment_id,
                "tid": tx_id,
            },
        )
        await session.execute(
            text("UPDATE payment_sessions SET status='COMPLETED' WHERE id=:sid"),
            {"sid": row.id},
        )
        await session.execute(
            text("UPDATE payment_capabilities SET used=1 WHERE transaction_id=:tid AND used=0"),
            {"tid": tx_id},
        )
        await session.execute(
            text(
                "INSERT INTO payment_events (id, transaction_id, event_type, payload_json) VALUES (:id, :tid, 'payment.verified', :payload)"
            ),
            {
                "id": str(uuid.uuid4()),
                "tid": tx_id,
                "payload": '{"status":"verified"}',
            },
        )
        await session.commit()
        _log.info(
            "Simulated payment for session %s: order=%s, payment=%s",
            req.payment_session_id,
            razorpay_order_id,
            razorpay_payment_id,
        )
        return SimulatePaymentResponse(
            success=True,
            payment_session_id=req.payment_session_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            status="VERIFIED",
            simulated=True,
        )


class MandateChargeRequest(BaseModel):
    """Request an autonomous charge against a pre-authorized mandate."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(..., description="Transaction UUID or display_id")
    authorization_id: str | None = Field(
        default=None, description="mandate.charge capability ID (defaults to the fresh one)"
    )
    mandate_id: str = Field(..., description="Mandate UUID or display_id")
    idempotency_key: str | None = Field(default=None, description="Replay guard")


class MandateChargeResponse(BaseModel):
    """Response from a mandate charge."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    transaction_id: str
    payment_id: str | None = None
    status: str
    reason: str | None = None


@router.post("/mandate-charge", response_model=MandateChargeResponse)
async def mandate_charge(req: MandateChargeRequest) -> MandateChargeResponse:
    """Charge a pre-authorized mandate (bounded autonomous execution).

    Blueprint Phase 8-13 order for autonomous charging:
      1. Bind mandate to tx.
      2. Idempotency replay guard FIRST (Phase 9) — same key returns the
         stored result without re-authorizing or re-charging.
      3. Validate transaction state (Phase 8) — a terminal/verified tx is
         never charged again, even under a fresh idempotency key.
      4. Governed authorize EXACTLY ONCE (mandate rule + existing pipeline)
         -> bounded session + one-time mandate.charge capability.
      5. Validate session/capability/amount (no adapter call on failure).
      6. Audit + provider charge.
      7. Success -> daily usage accrues, walk to PAYMENT_VERIFIED, settle.
         Decline -> PAYMENT_FAILED, session FAILED, no daily usage consumed.

    Verification note (two-layer, blueprint Phase 11): with the stub-first
    provider, the charge response is the only Layer-1 evidence, so a confirmed
    charge records PAYMENT_VERIFIED directly. This is an explicit, documented
    exception for the stub provider; when the live Razorpay mandate API is
    wired (blueprint non-goal, deferred), the HMAC-verified webhook leg
    (Layer 2) must gate PAYMENT_VERIFIED -> settlement exactly like the
    human-checkout path.
    """
    import json
    import uuid
    from datetime import UTC, datetime

    from sqlalchemy import text

    from paari.audit.logger import AUDIT
    from paari.db.engine import get_session_maker
    from paari.governance_engine.state_machine import walk_to
    from paari.schemas.audit import AuditDecision

    service = get_payment_service()
    maker = get_session_maker()
    request_id = str(uuid.uuid4())
    async with maker() as session:
        tx = (
            await session.execute(
                text(
                    "SELECT id, display_id, amount_paise, currency, state, mandate_id, "
                    "merchant_id, buyer_agent_id FROM transactions "
                    "WHERE id=:x OR display_id=:x"
                ),
                {"x": req.transaction_id},
            )
        ).first()
        if tx is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="transaction_not_found"
            )
        tx_id = tx.id
        tx_display = tx.display_id or tx_id
        amount = int(tx.amount_paise)
        currency = tx.currency or "INR"
        if tx.mandate_id and tx.mandate_id not in (req.mandate_id,):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="tx_mandate_mismatch"
            )
        mandate = (
            await session.execute(
                text(
                    "SELECT id, display_id, status, instrument_reference FROM mandates "
                    "WHERE id=:x OR display_id=:x"
                ),
                {"x": req.mandate_id},
            )
        ).first()
        if mandate is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mandate_not_found")
        if mandate.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="mandate_not_active"
            )
        if not tx.mandate_id:
            await session.execute(
                text("UPDATE transactions SET mandate_id=:m WHERE id=:t"),
                {"m": mandate.id, "t": tx_id},
            )
            await session.commit()

        idem_key = req.idempotency_key or f"mandate-charge:{tx_id}:{mandate.id}"
        prior = (
            await session.execute(
                text("SELECT response_json FROM idempotency_keys WHERE key=:k"),
                {"k": idem_key},
            )
        ).first()
        if prior:
            # Phase 9 replay: same key -> stored result. No re-authorize, no
            # re-charge, no orphaned session/capability rows.
            return MandateChargeResponse(**json.loads(prior.response_json))

        # Phase 8: validate transaction state before any authorization or
        # provider call. A verified/fulfilled/terminal tx is never charged
        # again, even under a fresh idempotency key (double-charge guard).
        if tx.state not in ("CREATED", "GOVERNANCE_PENDING", "AUTHORIZED", "PAYMENT_PENDING"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"tx_not_chargeable: {tx.state}",
            )

        await AUDIT.log(
            request_id=request_id,
            action="MANDATE_CHARGE_REQUESTED",
            decision=AuditDecision.ALLOW,
            merchant_id=tx.merchant_id,
            agent_id=tx.buyer_agent_id,
            payload={
                "mandate_id": mandate.display_id or mandate.id,
                "transaction_id": tx_display,
                "amount_paise": amount,
                "state": tx.state,
            },
        )

        # Authorize exactly once (blueprint Phase 5/7): governance evaluates
        # (MANDATE rule included); on ALLOW a bounded payment session plus a
        # one-time mandate.charge capability is created.
        auth = await service.authorize_mandate_charge(req.transaction_id)
        if not auth.authorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=auth.reason or "not_authorized"
            )

        await AUDIT.log(
            request_id=request_id,
            action="CHARGE_AUTHORIZED",
            decision=AuditDecision.ALLOW,
            merchant_id=tx.merchant_id,
            agent_id=tx.buyer_agent_id,
            payload={
                "mandate_id": mandate.display_id or mandate.id,
                "transaction_id": tx_display,
                "amount_paise": amount,
                "session_display_id": auth.session_display_id,
                "capability_display_id": auth.capability_display_id,
            },
        )

        cap_id = req.authorization_id or auth.capability_id
        cap = (
            await session.execute(
                text(
                    "SELECT id, max_amount, used FROM payment_capabilities "
                    "WHERE id=:c AND transaction_id=:t AND action='mandate.charge'"
                ),
                {"c": cap_id, "t": tx_id},
            )
        ).first()
        if cap is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="authorization_not_found"
            )
        if int(cap.used) != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="authorization_reused"
            )
        sess = (
            await session.execute(
                text(
                    "SELECT id, authorized_amount, status FROM payment_sessions WHERE transaction_id=:t AND status='ACTIVE'"
                ),
                {"t": tx_id},
            )
        ).first()
        if sess is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session_not_found")
        if int(sess.authorized_amount) != amount or int(cap.max_amount) != amount:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="amount_mismatch")

        # Audit BEFORE the money call (fail-closed: an audit gap means no charge).
        await AUDIT.log(
            request_id=request_id,
            action="RAZORPAY_CHARGE_REQUESTED",
            decision=AuditDecision.EXECUTED,
            merchant_id=tx.merchant_id,
            agent_id=tx.buyer_agent_id,
            payload={
                "mandate_id": mandate.display_id or mandate.id,
                "transaction_id": tx_display,
                "amount_paise": amount,
                "currency": currency,
            },
        )

        adapter = await service.get_adapter()
        try:
            charged = await adapter.charge_mandate(
                mandate.instrument_reference, amount, currency
            )
        except NotImplementedError:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="mandate_provider_not_integrated",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=f"provider_error: {exc}"
            )

        if not charged.get("success"):
            # Decline: no daily usage is consumed (accounting happens only on a
            # confirmed charge) and the bounded session is expired so a retry
            # starts clean.
            try:
                await walk_to(session, tx_id, "PAYMENT_FAILED")
            except Exception:
                await session.execute(
                    text("UPDATE transactions SET state='PAYMENT_FAILED' WHERE id=:t"), {"t": tx_id}
                )
            await session.execute(
                text(
                    "UPDATE payment_sessions SET status='FAILED' "
                    "WHERE transaction_id=:t AND status='ACTIVE'"
                ),
                {"t": tx_id},
            )
            await session.execute(
                text(
                    "INSERT INTO payment_events (id, transaction_id, event_type, payload_json) VALUES (:id, :t, 'payment.failed', :p)"
                ),
                {"id": uuid.uuid4().hex, "t": tx_id, "p": '{"source":"mandate"}'},
            )
            await session.commit()
            await AUDIT.log(
                request_id=request_id,
                action="RAZORPAY_CHARGE_DECLINED",
                decision=AuditDecision.FAILED,
                merchant_id=tx.merchant_id,
                agent_id=tx.buyer_agent_id,
                payload={
                    "mandate_id": mandate.display_id or mandate.id,
                    "transaction_id": tx_display,
                    "amount_paise": amount,
                    "reason": "provider_declined",
                },
            )
            return MandateChargeResponse(
                success=False,
                transaction_id=tx.display_id or tx_id,
                status="FAILED",
                reason="provider_declined",
            )

        payment_id = charged.get("payment_id")

        # Daily usage accrues ONLY on a confirmed charge: a decline or provider
        # error above never consumed the mandate's daily budget.
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        await session.execute(
            text(
                "INSERT INTO mandate_daily_usage (mandate_id, day, used_paise) VALUES (:m, :d, :u) "
                "ON CONFLICT(mandate_id, day) DO UPDATE SET used_paise = used_paise + :u"
            ),
            {"m": mandate.id, "d": day, "u": amount},
        )

        # Fail-closed transition: the state machine (not a raw UPDATE) moves a
        # chargeable tx to PAYMENT_VERIFIED. Illegal states raise instead of
        # silently charging.
        await walk_to(session, tx_id, "PAYMENT_VERIFIED")
        await session.execute(
            text("UPDATE transactions SET razorpay_payment_id=:p WHERE id=:t"),
            {"p": payment_id, "t": tx_id},
        )
        await session.execute(
            text(
                "UPDATE payment_sessions SET status='COMPLETED' WHERE transaction_id=:t AND status='ACTIVE'"
            ),
            {"t": tx_id},
        )
        await session.execute(
            text("UPDATE payment_capabilities SET used=1 WHERE id=:c"), {"c": cap.id}
        )
        await session.execute(
            text(
                "INSERT INTO payment_events (id, transaction_id, event_type, payload_json) VALUES (:id, :t, 'payment.verified', :p)"
            ),
            {"id": uuid.uuid4().hex, "t": tx_id, "p": '{"source":"mandate"}'},
        )
        resp = MandateChargeResponse(
            success=True,
            transaction_id=tx.display_id or tx_id,
            payment_id=payment_id,
            status="VERIFIED",
        )
        await session.execute(
            text(
                "INSERT INTO idempotency_keys (key, agent_id, action, response_json) VALUES (:k, :a, :act, :r) "
                "ON CONFLICT(key) DO NOTHING"
            ),
            {
                "k": idem_key,
                "a": "mandate-charge",
                "act": "mandate.charge",
                "r": resp.model_dump_json(),
            },
        )
        await session.commit()

        # Resolve the stored replay row: ours, or a racing duplicate's that
        # committed first. Same key must return the same result, so a
        # conflicting (already-stored) response wins deterministically.
        stored_row = (
            await session.execute(
                text("SELECT response_json FROM idempotency_keys WHERE key=:k"),
                {"k": idem_key},
            )
        ).first()
        if stored_row and stored_row.response_json != resp.model_dump_json():
            return MandateChargeResponse(**json.loads(stored_row.response_json))

        await AUDIT.log(
            request_id=request_id,
            action="RAZORPAY_PAYMENT_CONFIRMED",
            decision=AuditDecision.ALLOW,
            merchant_id=tx.merchant_id,
            agent_id=tx.buyer_agent_id,
            payload={
                "mandate_id": mandate.display_id or mandate.id,
                "transaction_id": tx_display,
                "amount_paise": amount,
                "payment_id": payment_id,
                "layer": "provider_response",
            },
        )

        try:
            from paari.payment.settle import settle_verified_transaction

            await settle_verified_transaction(tx_id)
        except Exception as exc:
            _log.warning("Post-charge settle failed: %s", exc)
        return resp
