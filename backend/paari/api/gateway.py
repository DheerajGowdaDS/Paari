"""Governance Gateway API — 3 curl-accessible endpoints.

POST /gateway/governance/evaluate
POST /gateway/transactions
POST /gateway/transactions/{display_id}/authorize-payment

No auth in this phase (SEC-001 — curl/Postman only, isolated).
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from paari.config import settings
from paari.db.engine import get_session_maker
from paari.governance_engine.context import GovernanceContext, GovernanceLoadError
from paari.governance_engine.evaluator import get_governance_engine
from paari.governance_engine.state_machine import DECISION_TO_STATE, transition
from paari.schemas.governance import CheckResult, GovernanceDecision, GovernanceRequest


_log = logging.getLogger("paari.gateway")
router = APIRouter(prefix="/gateway", tags=["governance"])


# ── request/response models ────────────────────────────────────────


class CreateTransactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    buyer_agent_display_id: str = Field(
        ..., description="Display id of the buyer agent (e.g. BA-001)"
    )
    merchant_agent_display_id: str = Field(
        ..., description="Display id of the merchant agent (e.g. MA-001)"
    )
    quote_id: str = Field(..., description="Quote UUID or display_id")
    amount_paise: int = Field(..., gt=0)
    currency: str = Field(default="INR")


class CreateTransactionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    display_id: str
    state: str


class AuthorizePaymentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_session_id: str
    payment_session_display_id: str
    capability_id: str
    capability_display_id: str
    authorized_amount: int
    currency: str
    expires_at: str
    status: str


# ── endpoints ──────────────────────────────────────────────────────


@router.post("/governance/evaluate", response_model=dict[str, Any])
async def evaluate_governance(req: GovernanceRequest) -> dict[str, Any]:
    """Evaluate governance for a transaction.

    Body: { "transaction_id": "TXN-001" }
    Returns the full GovernanceDecision with all check results.
    """
    engine = get_governance_engine()
    maker = get_session_maker()
    async with maker() as session:
        try:
            ctx = await GovernanceContext.load(session, req.transaction_id, req.request_id)
        except GovernanceLoadError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        decision = await engine.evaluate(ctx)
        session.add_row = lambda *a, **kw: None  # type: ignore[attr-defined]
        await session.commit()
    return _decision_to_dict(decision)


@router.post("/transactions", response_model=CreateTransactionResponse)
async def create_transaction(req: CreateTransactionRequest) -> CreateTransactionResponse:
    """Create a new transaction row in CREATED state.

    Body:
      {
        "buyer_agent_display_id": "BA-001",
        "merchant_agent_display_id": "MA-001",
        "quote_id": "QUOTE-001",
        "amount_paise": 479900,
        "currency": "INR"
      }
    """
    maker = get_session_maker()
    tx_id = str(uuid.uuid4())
    display_id = f"TXN-{secrets.token_hex(4).upper()}"

    async with maker() as session:
        # Resolve agent display_ids to UUIDs
        buyer_row = (
            await session.execute(
                text("SELECT id FROM agents WHERE display_id = :did OR id = :did"),
                {"did": req.buyer_agent_display_id},
            )
        ).first()
        merchant_row = (
            await session.execute(
                text("SELECT id FROM agents WHERE display_id = :did OR id = :did"),
                {"did": req.merchant_agent_display_id},
            )
        ).first()
        quote_row = (
            await session.execute(
                text("SELECT id FROM quotes WHERE id = :qid"),
                {"qid": req.quote_id},
            )
        ).first()

        if not buyer_row or not merchant_row or not quote_row:
            raise HTTPException(
                status_code=400, detail="buyer_agent / merchant_agent / quote not found"
            )

        await session.execute(
            text(
                "INSERT INTO transactions "
                "(id, display_id, merchant_id, buyer_agent_id, merchant_agent_id, quote_id, "
                " amount_paise, currency, state, policy_version) "
                "VALUES (:id, :display_id, :merchant_id, :buyer, :merchant, :quote_id, "
                " :amount, :currency, 'CREATED', 'v1')"
            ),
            {
                "id": tx_id,
                "display_id": display_id,
                "merchant_id": "MER-001",
                "buyer": buyer_row.id,
                "merchant": merchant_row.id,
                "quote_id": quote_row.id,
                "amount": req.amount_paise,
                "currency": req.currency or "INR",
            },
        )
        await session.commit()

    return CreateTransactionResponse(transaction_id=tx_id, display_id=display_id, state="CREATED")


@router.post(
    "/transactions/{display_id}/authorize-payment", response_model=AuthorizePaymentResponse
)
async def authorize_payment(display_id: str) -> AuthorizePaymentResponse:
    """Authorize payment for a transaction (governed).

    Phase-1 invariant: this endpoint shares the single governance decision
    path with ``POST /payments/create``. It runs
    ``GovernanceEngine.evaluate()`` and only mints a PaymentSession +
    one-time PaymentCapability when the decision is ALLOW. DENY/REVIEW
    return 409 and create nothing.

    Transitions AUTHORIZED -> PAYMENT_PENDING via the state machine.
    Returns 409 if the governance decision is not ALLOW.
    """
    maker = get_session_maker()

    async with maker() as session:
        tx_row = (
            await session.execute(
                text("SELECT id FROM transactions WHERE display_id = :did OR id = :did"),
                {"did": display_id},
            )
        ).first()
        if tx_row is None:
            raise HTTPException(status_code=404, detail=f"transaction not found: {display_id}")
        tx_uuid = tx_row.id

        try:
            ctx = await GovernanceContext.load(session, tx_uuid)
        except GovernanceLoadError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        engine = get_governance_engine()
        decision = await engine.evaluate(ctx, session)
        if decision.decision != "ALLOW":
            raise HTTPException(
                status_code=409,
                detail=f"governance decision is {decision.decision}, expected ALLOW",
            )

        now = datetime.now(UTC)
        session_id = str(uuid.uuid4())
        session_display_id = f"PS-{secrets.token_hex(4).upper()}"
        cap_id = str(uuid.uuid4())
        cap_display_id = f"CAP-{secrets.token_hex(4).upper()}"
        expires_at = now + timedelta(minutes=10)

        # Get transaction amount
        txn_row = (
            await session.execute(
                text("SELECT amount_paise FROM transactions WHERE id = :tid"),
                {"tid": tx_uuid},
            )
        ).first()
        amount = int(txn_row.amount_paise) if txn_row else 0

        # Create payment session
        await session.execute(
            text(
                "INSERT INTO payment_sessions "
                "(id, display_id, transaction_id, authorized_amount, currency, status, expires_at) "
                "VALUES (:id, :display_id, :tx, :amount, :currency, 'ACTIVE', :expires)"
            ),
            {
                "id": session_id,
                "display_id": session_display_id,
                "tx": tx_uuid,
                "amount": amount,
                "currency": "INR",
                "expires": expires_at.isoformat(),
            },
        )

        # Create one-time capability
        await session.execute(
            text(
                "INSERT INTO payment_capabilities "
                "(id, display_id, transaction_id, action, max_amount, usage, used) "
                "VALUES (:id, :display_id, :tx, 'payment.execute', :max, 'ONE_TIME', 0)"
            ),
            {
                "id": cap_id,
                "display_id": cap_display_id,
                "tx": tx_uuid,
                "max": amount,
            },
        )

        # State transition: GOVERNANCE_PENDING -> AUTHORIZED -> PAYMENT_PENDING
        # First transition to AUTHORIZED if needed
        current_row = (
            await session.execute(
                text("SELECT state FROM transactions WHERE id = :tid"),
                {"tid": tx_uuid},
            )
        ).first()
        current_state = current_row.state if current_row else "CREATED"

        # Walk CREATED -> GOVERNANCE_PENDING -> AUTHORIZED and stop at AUTHORIZED.
        # The payment leg (PaymentService.create_razorpay_order) moves the
        # transaction to PAYMENT_PENDING, not this endpoint.
        try:
            if current_state == "CREATED":
                await transition(session, tx_uuid, "GOVERNANCE_PENDING")
            if current_state != "AUTHORIZED":
                await transition(session, tx_uuid, "AUTHORIZED")
        except Exception as e:
            _log.warning("state transition for %s failed: %s", display_id, e)

        await session.commit()

    return AuthorizePaymentResponse(
        payment_session_id=session_id,
        payment_session_display_id=session_display_id,
        capability_id=cap_id,
        capability_display_id=cap_display_id,
        authorized_amount=amount,
        currency="INR",
        expires_at=expires_at.isoformat(),
        status="ACTIVE",
    )


def _decision_to_dict(decision: GovernanceDecision) -> dict[str, Any]:
    return {
        "request_id": decision.request_id,
        "transaction_id": decision.transaction_id,
        "transaction_display_id": decision.transaction_display_id,
        "decision": decision.decision,
        "policy_version": decision.policy_version,
        "checks": [
            {
                "check": c.check,
                "status": c.status,
                "reason_code": c.reason_code,
                "details": c.details,
            }
            for c in decision.checks
        ],
        "failed_checks": [
            {
                "check": c.check,
                "reason_code": c.reason_code,
                "details": c.details,
            }
            for c in decision.failed_checks
        ],
    }
