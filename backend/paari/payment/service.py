"""Payment orchestration service.

Orchestrates the payment flow:
1. Governance evaluation (ALLOW/DENY/REVIEW)
2. Payment session creation
3. Razorpay order creation
4. Payment verification
5. Webhook simulation (for demo)
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from sqlalchemy import text

from paari.config import settings
from paari.db.engine import get_session_maker
from paari.governance_engine.context import GovernanceContext, GovernanceLoadError
from paari.governance_engine.evaluator import get_governance_engine
from paari.governance_engine.state_machine import transition, walk_to

_log = logging.getLogger("paari.payment")


class PaymentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class PaymentEventType(str, Enum):
    ORDER_CREATED = "payment.order_created"
    PAYMENT_VERIFY = "payment.verify"
    WEBHOOK_RECEIVED = "payment.webhook_received"
    FULFILLED = "payment.fulfilled"


@dataclass
class PaymentSession:
    """Represents an active payment session."""

    id: str
    display_id: str
    transaction_id: str
    authorized_amount: int
    currency: str
    status: PaymentStatus
    expires_at: datetime


@dataclass
class PaymentCapability:
    """Represents a payment capability for a transaction."""

    id: str
    display_id: str
    transaction_id: str
    action: str
    max_amount: int
    usage: str
    used: bool


@dataclass
class AuthorizeResult:
    """Result of authorize_payment operation."""

    authorized: bool
    session_id: str | None = None
    session_display_id: str | None = None
    capability_id: str | None = None
    capability_display_id: str | None = None
    authorized_amount: int | None = None
    currency: str | None = None
    expires_at: str | None = None
    reason: str | None = None


@dataclass
class PaymentResult:
    """Result of a payment operation."""

    success: bool
    order_id: str | None = None
    payment_id: str | None = None
    status: str | None = None
    reason: str | None = None


@dataclass
class PaymentService:
    """Orchestrates payment flow through governance → Razorpay → webhook.

    Integrates with:
    - GovernanceEngine for authorization decisions
    - Razorpay adapter (stub or live) for payment processing
    - Database for session/capability persistence
    """

    governance_engine: Any = field(default=None)
    razorpay_adapter: Any = field(default=None)
    session_maker: Any = field(default=None)

    def __post_init__(self) -> None:
        if self.governance_engine is None:
            self.governance_engine = get_governance_engine()
        if self.session_maker is None:
            self.session_maker = get_session_maker()

    async def get_adapter(self) -> Any:
        """Get the configured Razorpay adapter (stub or live)."""
        if self.razorpay_adapter is not None:
            return self.razorpay_adapter

        from paari.config import settings

        if settings.razorpay_mode == "live":
            from paari.adapters.razorpay_live import get_razorpay_adapter

            return get_razorpay_adapter()
        else:
            from paari.tools.adapters.razorpay_stub import get_razorpay_stub_adapter

            return get_razorpay_stub_adapter()

    async def create_payment_session(
        self,
        transaction_id: str,
        db_session=None,
    ) -> PaymentSession:
        """Create a payment session for a transaction.

        Args:
            transaction_id: UUID or display_id of the transaction.
            db_session: Optional existing session. If not provided, creates a new one.

        Returns:
            PaymentSession instance.
        """

        async def _create(session: Any) -> PaymentSession:
            tx_row = (
                await session.execute(
                    text(
                        "SELECT id, amount_paise, currency FROM transactions WHERE id = :x OR display_id = :x"
                    ),
                    {"x": transaction_id},
                )
            ).first()
            if tx_row is None:
                raise ValueError(f"Transaction not found: {transaction_id}")

            tx_id = tx_row.id
            amount = int(tx_row.amount_paise)
            currency = tx_row.currency or "INR"

            session_id = secrets.token_hex(16)
            session_display_id = f"PS-{secrets.token_hex(4).upper()}"
            now = datetime.now(UTC)
            expires_at = now + timedelta(minutes=10)

            await session.execute(
                text(
                    "INSERT INTO payment_sessions "
                    "(id, display_id, transaction_id, authorized_amount, currency, status, expires_at) "
                    "VALUES (:id, :display_id, :tx, :amount, :currency, :status, :expires)"
                ),
                {
                    "id": session_id,
                    "display_id": session_display_id,
                    "tx": tx_id,
                    "amount": amount,
                    "currency": currency,
                    "status": "ACTIVE",
                    "expires": expires_at.isoformat(),
                },
            )

            return PaymentSession(
                id=session_id,
                display_id=session_display_id,
                transaction_id=tx_id,
                authorized_amount=amount,
                currency=currency,
                status=PaymentStatus.ACTIVE,
                expires_at=expires_at,
            )

        if db_session is not None:
            return await _create(db_session)

        maker = self.session_maker
        async with maker() as session:
            result = await _create(session)
            await session.commit()
            return result

    async def create_payment_capability(
        self,
        transaction_id: str,
        action: str = "payment.execute",
        db_session=None,
    ) -> PaymentCapability:
        """Create a one-time payment capability for a transaction.

        Args:
            transaction_id: UUID or display_id of the transaction.
            action: Capability action (default: payment.execute).
            db_session: Optional existing session. If not provided, creates a new one.

        Returns:
            PaymentCapability instance.
        """

        async def _create(session: Any) -> PaymentCapability:
            tx_row = (
                await session.execute(
                    text(
                        "SELECT id, amount_paise FROM transactions WHERE id = :x OR display_id = :x"
                    ),
                    {"x": transaction_id},
                )
            ).first()
            if tx_row is None:
                raise ValueError(f"Transaction not found: {transaction_id}")

            tx_id = tx_row.id
            max_amount = int(tx_row.amount_paise)

            cap_id = secrets.token_hex(16)
            cap_display_id = f"CAP-{secrets.token_hex(4).upper()}"

            await session.execute(
                text(
                    "INSERT INTO payment_capabilities "
                    "(id, display_id, transaction_id, action, max_amount, usage, used) "
                    "VALUES (:id, :display_id, :tx, :action, :max, 'ONE_TIME', 0)"
                ),
                {
                    "id": cap_id,
                    "display_id": cap_display_id,
                    "tx": tx_id,
                    "action": action,
                    "max": max_amount,
                },
            )

            return PaymentCapability(
                id=cap_id,
                display_id=cap_display_id,
                transaction_id=tx_id,
                action=action,
                max_amount=max_amount,
                usage="ONE_TIME",
                used=False,
            )

        if db_session is not None:
            return await _create(db_session)

        maker = self.session_maker
        async with maker() as session:
            result = await _create(session)
            await session.commit()
            return result

    async def authorize_payment(self, transaction_id: str) -> AuthorizeResult:
        """Authorize payment for a transaction through governance.

        1. Load governance context
        2. Evaluate governance rules
        3. If ALLOW: create session + capability, transition to PAYMENT_PENDING
        4. If DENY/REVIEW: return unauthorized result

        Args:
            transaction_id: UUID or display_id of the transaction.

        Returns:
            AuthorizeResult with authorization status and session/capability IDs.
        """
        maker = self.session_maker
        async with maker() as session:
            try:
                ctx = await GovernanceContext.load(session, transaction_id)
            except GovernanceLoadError as exc:
                return AuthorizeResult(authorized=False, reason=str(exc))

            decision = await self.governance_engine.evaluate(ctx, session)

            if decision.decision == "DENY":
                failed_checks = [c.reason_code for c in decision.failed_checks]
                reason = f"governance_denied: {', '.join(failed_checks)}"
                try:
                    await walk_to(session, ctx.transaction.id, "DENIED")
                    await session.commit()
                except Exception as e:
                    _log.warning("Failed to transition to DENIED for %s: %s", transaction_id, e)
                return AuthorizeResult(authorized=False, reason=reason)

            if decision.decision == "REVIEW":
                try:
                    await walk_to(session, ctx.transaction.id, "REVIEW_REQUIRED")
                    await session.commit()
                except Exception as e:
                    _log.warning(
                        "Failed to transition to REVIEW_REQUIRED for %s: %s", transaction_id, e
                    )
                return AuthorizeResult(authorized=False, reason="review_required")

            if decision.decision != "ALLOW":
                return AuthorizeResult(
                    authorized=False,
                    reason=f"unexpected_decision: {decision.decision}",
                )

            try:
                await walk_to(session, ctx.transaction.id, "AUTHORIZED")
                await transition(session, ctx.transaction.id, "PAYMENT_PENDING")
            except Exception as e:
                _log.warning("State transition issue for %s: %s", transaction_id, e)

            payment_session = await self.create_payment_session(transaction_id, db_session=session)
            capability = await self.create_payment_capability(transaction_id, db_session=session)

            await session.commit()

            return AuthorizeResult(
                authorized=True,
                session_id=payment_session.id,
                session_display_id=payment_session.display_id,
                capability_id=capability.id,
                capability_display_id=capability.display_id,
                authorized_amount=payment_session.authorized_amount,
                currency=payment_session.currency,
                expires_at=payment_session.expires_at.isoformat(),
            )

    async def authorize_mandate_charge(self, transaction_id: str) -> AuthorizeResult:
        """Authorize an autonomous mandate charge for a transaction.

        Mirrors authorize_payment: governance evaluates (including the
        MANDATE rule when the tx carries a mandate_id); on ALLOW the tx
        walks to PAYMENT_PENDING with a fresh session plus a one-time
        ``mandate.charge`` capability. Returns AuthorizeResult.
        """
        maker = self.session_maker
        async with maker() as session:
            try:
                ctx = await GovernanceContext.load(session, transaction_id)
            except GovernanceLoadError as exc:
                return AuthorizeResult(authorized=False, reason=str(exc))

            decision = await self.governance_engine.evaluate(ctx, session)

            if decision.decision == "DENY":
                failed_checks = [c.reason_code for c in decision.failed_checks]
                reason = f"governance_denied: {', '.join(failed_checks)}"
                try:
                    await walk_to(session, ctx.transaction.id, "DENIED")
                    await session.commit()
                except Exception as e:
                    _log.warning("Failed to transition to DENIED for %s: %s", transaction_id, e)
                return AuthorizeResult(authorized=False, reason=reason)

            if decision.decision == "REVIEW":
                try:
                    await walk_to(session, ctx.transaction.id, "REVIEW_REQUIRED")
                    await session.commit()
                except Exception as e:
                    _log.warning(
                        "Failed to transition to REVIEW_REQUIRED for %s: %s", transaction_id, e
                    )
                return AuthorizeResult(authorized=False, reason="review_required")

            if decision.decision != "ALLOW":
                return AuthorizeResult(
                    authorized=False,
                    reason=f"unexpected_decision: {decision.decision}",
                )

            try:
                await walk_to(session, ctx.transaction.id, "AUTHORIZED")
                await transition(session, ctx.transaction.id, "PAYMENT_PENDING")
            except Exception as e:
                _log.warning("State transition issue for %s: %s", transaction_id, e)

            payment_session = await self.create_payment_session(transaction_id, db_session=session)
            capability = await self.create_payment_capability(
                transaction_id, action="mandate.charge", db_session=session
            )

            await session.commit()

            return AuthorizeResult(
                authorized=True,
                session_id=payment_session.id,
                session_display_id=payment_session.display_id,
                capability_id=capability.id,
                capability_display_id=capability.display_id,
                authorized_amount=payment_session.authorized_amount,
                currency=payment_session.currency,
                expires_at=payment_session.expires_at.isoformat(),
            )

    async def create_razorpay_order(
        self,
        transaction_id: str,
        session_id: str,
    ) -> PaymentResult:
        """Create a Razorpay order for an authorized transaction.

        Bounded money touch (Phase-1 invariant): the order amount is
        exactly ``session.authorized_amount`` and only when the session
        exists, belongs to this tx, is ACTIVE (and unexpired), and matches
        the tx amount. Any failure returns ``success=False`` with a typed
        reason and NEVER calls the adapter.

        Typed reasons: ``transaction_not_found``,
        ``invalid_transaction_state``, ``session_not_found``,
        ``session_not_active``, ``session_tx_mismatch``, ``amount_mismatch``.

        Args:
            transaction_id: UUID or display_id of the transaction.
            session_id: Payment session ID (UUID or display_id).

        Returns:
            PaymentResult with order details.
        """
        maker = self.session_maker

        async with maker() as session:
            tx_row = (
                await session.execute(
                    text(
                        "SELECT t.id, t.amount_paise, t.currency, t.state "
                        "FROM transactions t WHERE t.id = :x OR t.display_id = :x"
                    ),
                    {"x": transaction_id},
                )
            ).first()
            if tx_row is None:
                return PaymentResult(success=False, reason="transaction_not_found")

            tx_id = tx_row.id
            amount = int(tx_row.amount_paise)
            currency = tx_row.currency or "INR"

            if tx_row.state not in ("PAYMENT_PENDING", "AUTHORIZED"):
                return PaymentResult(
                    success=False,
                    reason=f"invalid_transaction_state: {tx_row.state}",
                )

            sess_row = (
                await session.execute(
                    text(
                        "SELECT id, transaction_id, authorized_amount, currency, "
                        "status, expires_at FROM payment_sessions "
                        "WHERE id = :s OR display_id = :s"
                    ),
                    {"s": session_id},
                )
            ).first()
            if sess_row is None:
                return PaymentResult(success=False, reason="session_not_found")

            if sess_row.status != "ACTIVE":
                return PaymentResult(success=False, reason="session_not_active")

            try:
                expires = datetime.fromisoformat(str(sess_row.expires_at))
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=UTC)
                if expires <= datetime.now(UTC):
                    return PaymentResult(success=False, reason="session_not_active")
            except (ValueError, TypeError):
                pass

            if sess_row.transaction_id != tx_id:
                return PaymentResult(success=False, reason="session_tx_mismatch")

            if int(sess_row.authorized_amount) != amount:
                return PaymentResult(success=False, reason="amount_mismatch")

            bounded_amount = int(sess_row.authorized_amount)
            bounded_currency = sess_row.currency or currency

            adapter = await self.get_adapter()
            try:
                order_result = await adapter.create_order(
                    amount_paise=bounded_amount,
                    currency=bounded_currency,
                    receipt=f"txn_{tx_id[:8]}",
                    notes={"transaction_id": tx_id, "session_id": sess_row.id},
                )

                order_id = order_result.get("order_id")
                if not order_id:
                    return PaymentResult(success=False, reason="order_creation_failed")

                await session.execute(
                    text(
                        "UPDATE transactions SET razorpay_order_id = :oid, payment_session_id = :sid "
                        "WHERE id = :tid"
                    ),
                    {"oid": order_id, "sid": sess_row.id, "tid": tx_id},
                )
                await session.commit()

                return PaymentResult(
                    success=True,
                    order_id=order_id,
                    status="created",
                )
            except Exception as exc:
                _log.error("Razorpay order creation failed: %s", exc)
                return PaymentResult(success=False, reason=f"order_creation_error: {exc}")

    async def verify_payment_signature(
        self,
        payment_id: str,
        order_id: str,
        signature: str,
        payload: bytes | None = None,
    ) -> bool:
        """Verify payment signature from Razorpay checkout.

        Razorpay signs f"{order_id}|{payment_id}" with the key secret; the
        raw request body is not part of this scheme.

        Args:
            payment_id: Razorpay payment ID.
            order_id: Razorpay order ID.
            signature: razorpay_signature from checkout.
            payload: Unused legacy parameter, kept for compatibility.

        Returns:
            True if signature is valid.
        """
        adapter = await self.get_adapter()
        return await adapter.verify_checkout_signature(order_id, payment_id, signature)

    async def simulate_webhook(
        self,
        event_type: str,
        payment_id: str,
        order_id: str,
        amount: int,
    ) -> None:
        """Fire a synthetic webhook event for demo/testing.

        This bypasses the actual Razorpay webhook and directly calls
        the handler with a properly signed event.

        Args:
            event_type: Event type (e.g., 'payment.captured').
            payment_id: Payment ID.
            order_id: Order ID.
            amount: Amount in paise.
        """
        adapter = await self.get_adapter()

        payload_dict = {
            "event": event_type,
            "id": f"evt_{secrets.token_hex(8)}",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": amount,
                        "status": "captured" if "captured" in event_type else "failed",
                    }
                }
            },
        }

        payload_bytes = json.dumps(payload_dict).encode()
        signature = await adapter.generate_signature(payload_bytes)

        from paari.webhooks.razorpay_handler import handle_razorpay_event

        webhook_event = {
            "event": event_type,
            "id": payload_dict["id"],
            "payload": payload_dict["payload"],
            "signature": signature,
            "synthetic": True,
        }

        await handle_razorpay_event(webhook_event)

    async def record_payment_event(
        self,
        transaction_id: str,
        event_type: PaymentEventType,
        payload: dict[str, Any],
    ) -> None:
        """Record a payment event to the database.

        Args:
            transaction_id: Transaction UUID.
            event_type: Type of payment event.
            payload: Event payload as dict.
        """
        maker = self.session_maker
        async with maker() as session:
            event_id = str(secrets.token_hex(16))
            await session.execute(
                text(
                    "INSERT INTO payment_events (id, transaction_id, event_type, payload_json) "
                    "VALUES (:id, :tx, :type, :payload)"
                ),
                {
                    "id": event_id,
                    "tx": transaction_id,
                    "type": event_type.value,
                    "payload": json.dumps(payload),
                },
            )
            await session.commit()


_payment_service: PaymentService | None = None


def get_payment_service() -> PaymentService:
    """Get the singleton PaymentService instance."""
    global _payment_service
    if _payment_service is None:
        _payment_service = PaymentService()
    return _payment_service
